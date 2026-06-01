import sys
from PyQt6.QtWidgets import QApplication, QLabel

app = QApplication(sys.argv)
label = QLabel("Hello PyQt6!")
label.show()
sys.exit(app.exec())