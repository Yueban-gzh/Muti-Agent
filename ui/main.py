import sys
from PyQt6.QtWidgets import QApplication
from ui.login_widget import LoginWidget

def main():
    app = QApplication(sys.argv)
    # 加载 QSS 样式
    with open("ui/style.qss", "r", encoding="utf-8") as f:
        qss = f.read()
    app.setStyleSheet(qss)
    
    login = LoginWidget()
    login.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()