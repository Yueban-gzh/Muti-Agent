import sys
from PyQt6.QtWidgets import QApplication
from ui.login_widget import LoginWidget

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    login = LoginWidget()
    login.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()