"""
KV Cache 预分配池 + Prefix Cache (Radix Tree)。

物理布局：
  K/V 各自分配一个连续大 buffer:
    shape = [total_tokens, num_layers, num_kv_heads, head_dim]

每个请求分配一段连续的 token-level 切片，free 时回收 slot。

Prefix Cache:
  Radix Tree 存储 (token_hash → KV cache offset) 映射，
  新请求先查树找到最长公共前缀，直接复用 KV cache，
  省去重复 prefill。
"""

from __future__ import annotations

import torch
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import threading


@dataclass
class CacheBlock:
    """KV Cache 中一段连续的 token slot。"""

    start: int  # 在 buffer 中的起始 token 位置
    length: int  # token 数
    ref_count: int = 1  # 引用计数（被 prefix cache 引用时 +1）

    @property
    def end(self) -> int:
        return self.start + self.length

    def slice(self) -> slice:
        return slice(self.start, self.end)


class FreeList:
    """自由 slot 管理器（LIFO + 合并相邻空闲块）。"""

    def __init__(self, total_tokens: int):
        self.total_tokens = total_tokens
        # 用区间树存储空闲块: [(start, length), ...]
        self._free_blocks: List[Tuple[int, int]] = [(0, total_tokens)]
        self._lock = threading.Lock()

    def alloc(self, num_tokens: int) -> Optional[int]:
        """分配 num_tokens 个连续 slot，返回起始位置。Best-fit。"""
        with self._lock:
            best_idx = -1
            best_waste = float("inf")
            for i, (start, length) in enumerate(self._free_blocks):
                if length >= num_tokens:
                    waste = length - num_tokens
                    if waste < best_waste:
                        best_waste = waste
                        best_idx = i
                        if waste == 0:
                            break

            if best_idx == -1:
                return None

            start, length = self._free_blocks[best_idx]
            if length == num_tokens:
                self._free_blocks.pop(best_idx)
            else:
                self._free_blocks[best_idx] = (start + num_tokens, length - num_tokens)

            return start

    def free(self, start: int, num_tokens: int):
        """释放 slot，与相邻空闲块合并。"""
        with self._lock:
            insert_idx = 0
            for i, (s, l) in enumerate(self._free_blocks):
                if s > start:
                    insert_idx = i
                    break
                insert_idx = i + 1

            # 尝试与前后相邻块合并
            new_start, new_len = start, num_tokens

            # 与前一块合并
            if insert_idx > 0:
                prev_start, prev_len = self._free_blocks[insert_idx - 1]
                if prev_start + prev_len == new_start:
                    new_start = prev_start
                    new_len += prev_len
                    self._free_blocks.pop(insert_idx - 1)
                    insert_idx -= 1

            # 与后一块合并
            if insert_idx < len(self._free_blocks):
                next_start, next_len = self._free_blocks[insert_idx]
                if new_start + new_len == next_start:
                    new_len += next_len
                    self._free_blocks.pop(insert_idx)

            self._free_blocks.insert(insert_idx, (new_start, new_len))


class RadixNode:
    """Radix Tree 节点，存储 token 到 KV cache 的映射。"""

    __slots__ = ("token_hash", "children", "cache_start", "cache_length", "ref_count")

    def __init__(self, token_hash: int):
        self.token_hash = token_hash
        self.children: dict[int, RadixNode] = {}
        self.cache_start: int = -1  # KV cache 中的起始位置，-1 表示无缓存
        self.cache_length: int = 0
        self.ref_count: int = 0  # 被多少请求引用


class PrefixCache:
    """Radix Tree 前缀缓存。

    存储 token 序列 → KV cache offset 映射。
    新请求先查树找到最长公共前缀，直接复用 prefill 结果。
    """

    def __init__(self, max_entries: int = 64):
        self.root = RadixNode(-1)  # 根节点
        self.max_entries = max_entries
        self.num_entries = 0
        self._lock = threading.Lock()

    def find_longest_prefix(self, token_ids: List[int]) -> Tuple[int, int]:
        """查找 token_ids 的最长可缓存前缀。

        Returns:
            (matched_length, cache_start): 匹配的 token 数和 KV cache 起始位置。
            如果 cache_start == -1，表示无匹配。
        """
        with self._lock:
            node = self.root
            matched = 0
            last_cache_start = -1
            last_cache_length = 0

            for token in token_ids:
                token_hash = hash(token) & 0x7FFFFFFF
                if token_hash not in node.children:
                    break
                node = node.children[token_hash]
                matched += 1
                if node.cache_start >= 0:
                    last_cache_start = node.cache_start
                    last_cache_length = node.cache_length

            return matched, last_cache_start

    def insert(self, token_ids: List[int], cache_start: int, cache_length: int):
        """插入前缀到缓存。"""
        with self._lock:
            if self.num_entries >= self.max_entries:
                self._evict_one()

            node = self.root
            for i, token in enumerate(token_ids):
                token_hash = hash(token) & 0x7FFFFFFF
                if token_hash not in node.children:
                    node.children[token_hash] = RadixNode(token_hash)
                node = node.children[token_hash]
                if i == len(token_ids) - 1:
                    node.cache_start = cache_start
                    node.cache_length = cache_length
                    self.num_entries += 1

    def _evict_one(self):
        """LRU 驱逐一个条目。简单策略：驱逐根节点的第一个叶子。"""
        def _evict_leaf(node: RadixNode, depth: int) -> bool:
            if not node.children:
                if node.cache_start >= 0:
                    node.cache_start = -1
                    node.cache_length = 0
                    self.num_entries -= 1
                    return True
                return False
            for child in list(node.children.values()):
                if _evict_leaf(child, depth + 1):
                    if not child.children and child.cache_start < 0:
                        del node.children[child.token_hash]
                    return True
            return False

        _evict_leaf(self.root, 0)


class KVCachePool:
    """预分配的 KV Cache 池。

    为 Hunyuan GQA 优化：
      K/V 各自 [total_tokens, num_layers, num_kv_heads, head_dim]

    用法:
      pool = KVCachePool(total_tokens=32768, ...)
      block = pool.alloc(128)  # 分配 128 个 token slot
      k_slice = pool.get_k_slice(block)  # → shape [128, 32, 8, 128]
      # ... prefill / decode ...
      pool.free(block)
    """

    def __init__(
        self,
        total_tokens: int,
        num_layers: int,
        num_kv_heads: int,
        head_dim: int,
        dtype: torch.dtype = torch.float16,
        device: str = "cuda",
    ):
        self.total_tokens = total_tokens
        self.num_layers = num_layers
        self.num_kv_heads = num_kv_heads
        self.head_dim = head_dim

        shape = (total_tokens, num_layers, num_kv_heads, head_dim)

        # 预分配大 buffer
        self.k_buffer = torch.empty(shape, dtype=dtype, device=device)
        self.v_buffer = torch.empty(shape, dtype=dtype, device=device)

        self.free_list = FreeList(total_tokens)

        # 已分配的 block 映射
        self._blocks: dict[int, CacheBlock] = {}  # start → CacheBlock
        self._lock = threading.Lock()

        # 统计
        self.alloc_count = 0
        self.free_count = 0
        self.peak_usage = 0

    def alloc(self, num_tokens: int) -> Optional[CacheBlock]:
        """分配 num_tokens 个连续 token slot。"""
        start = self.free_list.alloc(num_tokens)
        if start is None:
            return None

        block = CacheBlock(start=start, length=num_tokens)
        with self._lock:
            self._blocks[start] = block

        self.alloc_count += 1
        used = self.total_tokens - self.free_space
        if used > self.peak_usage:
            self.peak_usage = used
        return block

    def free(self, block: CacheBlock):
        """释放 block。"""
        with self._lock:
            if block.ref_count > 1:
                block.ref_count -= 1
                return
            self._blocks.pop(block.start, None)
        self.free_list.free(block.start, block.length)
        self.free_count += 1

    def add_ref(self, block: CacheBlock):
        """增加引用计数（被 prefix cache 引用时）。"""
        block.ref_count += 1

    def get_k_slice(self, block: CacheBlock, start: int = 0, length: Optional[int] = None) -> torch.Tensor:
        """获取 K tensor 的视图，shape [length, num_layers, num_kv_heads, head_dim]"""
        if length is None:
            length = block.length - start
        slc = slice(block.start + start, block.start + start + length)
        return self.k_buffer[slc]

    def get_v_slice(self, block: CacheBlock, start: int = 0, length: Optional[int] = None) -> torch.Tensor:
        """获取 V tensor 的视图。"""
        if length is None:
            length = block.length - start
        slc = slice(block.start + start, block.start + start + length)
        return self.v_buffer[slc]

    @property
    def free_space(self) -> int:
        return sum(l for _, l in self.free_list._free_blocks)

    @property
    def used_space(self) -> int:
        return self.total_tokens - self.free_space

    def clear(self):
        """清空整个 cache。"""
        with self._lock:
            self._blocks.clear()
        self.free_list = FreeList(self.total_tokens)
        self.k_buffer.zero_()
        self.v_buffer.zero_()
        self.peak_usage = 0
