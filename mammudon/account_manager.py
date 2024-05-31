import os
import re
import base64

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import QWidget, QCheckBox, QComboBox, QPushButton, QLineEdit
from PyQt6.uic import loadUi

from mammudon.account import Account
from mammudon.debugging import debug
from mammudon.prefs import preferences


class AccountManager(QWidget):
	add_login = pyqtSignal(object)

	def __init__(self):
		super().__init__()

		loadUi(os.path.join(os.path.dirname(__file__), "ui", "account_manager.ui"), self)

		self.close_button: QPushButton = self.findChild(QPushButton, "closeBtn")
		self.logins_combo: QComboBox = self.findChild(QComboBox, "loginsCombo")
		self.instance_edit: QLineEdit = self.findChild(QLineEdit, "instanceEdit")
		self.login_edit: QLineEdit = self.findChild(QLineEdit, "loginEdit")
		self.password_edit: QLineEdit = self.findChild(QLineEdit, "passwordEdit")
		self.save_login_check: QCheckBox = self.findChild(QCheckBox, "saveLoginCheck")
		self.autologin_check: QCheckBox = self.findChild(QCheckBox, "autologinCheck")
		self.delete_login_button: QPushButton = self.findChild(QPushButton, "deleteLoginBtn")
		self.login_button: QPushButton = self.findChild(QPushButton, "loginBtn")
		self.save_button: QPushButton = self.findChild(QPushButton, "saveBtn")

		self.login_button.setEnabled(False)

		self.logins_combo.currentIndexChanged.connect(self.saved_login_chosen)
		self.delete_login_button.clicked.connect(self.delete_login_button_pressed)
		self.login_edit.textChanged.connect(self.validate_login_form)
		self.password_edit.textChanged.connect(self.validate_login_form)
		self.login_button.clicked.connect(self.login_button_pressed)
		self.save_button.clicked.connect(self.save_button_pressed)

		# TODO: make these configurable or dynamic in some way
		self.setMaximumWidth(350)
		self.setMinimumWidth(350)

		settings = QSettings()
		settings.beginGroup("Accounts")

		for account_username in settings.allKeys():
			self.logins_combo.addItem(account_username)

		settings.endGroup()

		self.chosen_account_data = {}

		self.validate_login_form()

	def __del__(self):
		debug("__del__eting account manager")

	def login_button_pressed(self) -> None:
		instance = self.instance_edit.text()
		login = self.login_edit.text()
		password = self.password_edit.text()

		# add https:// to instance name if neither http:// nor https:// was given
		if not instance.startswith("https://"):
			if not instance.startswith("http://"):
				instance = "https://" + instance

		account = Account({
			# pick these 3 from the form so an account can be updated
			"login": login,
			"password": password,
			"instance": instance,

			# TODO: make configurable per account
			"feature_set": preferences.values["feature_set"],

			# these come from the saved settings
			"client_id": self.chosen_account_data.get("client_id", ""),
			"client_secret": self.chosen_account_data.get("client_secret", ""),
			"access_token": self.chosen_account_data.get("access_token", ""),
			"autologin": self.chosen_account_data.get("autologin", False)
		})

		self.add_login.emit(account)
		debug("Sent add_login signal")

	def saved_login_chosen(self, chosen_index: int) -> None:
		if chosen_index:
			chosen_login = self.logins_combo.currentText()

			settings = QSettings()
			settings.beginGroup("Accounts")
			self.chosen_account_data = dict(settings.value(chosen_login))
			self.instance_edit.setText(self.chosen_account_data["instance"])
			self.login_edit.setText(self.chosen_account_data["login"])
			self.password_edit.setText(base64.b64decode(self.chosen_account_data["password"]).decode("utf-8"))
			self.autologin_check.setChecked(self.chosen_account_data.get("autologin", False))
			settings.endGroup()
		else:
			self.chosen_account_data.clear()
			self.instance_edit.setText("")
			self.login_edit.setText("")
			self.password_edit.setText("")
			self.autologin_check.setChecked(False)

	def delete_login_button_pressed(self) -> None:
		username_to_delete = self.logins_combo.currentText()

		settings = QSettings()
		settings.beginGroup("Accounts")
		settings.remove(username_to_delete)
		settings.endGroup()

		self.logins_combo.removeItem(self.logins_combo.currentIndex())

	def validate_login_form(self) -> None:
		login_credentials_valid = False

		if self.instance_edit.text():
			if self.password_edit.text():
				if re.search("^[^@]+@.+.[a-zA-Z]+$", self.login_edit.text()):
					login_credentials_valid = True

		self.delete_login_button.setEnabled(bool(self.logins_combo.currentIndex()))
		self.login_button.setEnabled(login_credentials_valid)
		self.save_button.setEnabled(login_credentials_valid)

	def save_button_pressed(self, _clicked_unused: bool = True) -> None:
		settings = QSettings()
		settings.beginGroup("Accounts")

		account = dict(settings.value(self.logins_combo.currentText()))
		account["login"] = self.login_edit.text()
		account["password"] = base64.b64encode(bytes(self.password_edit.text(), "utf-8"))
		account["instance"] = self.instance_edit.text()
		account["autologin"] = self.autologin_check.isChecked()

		settings.setValue(self.logins_combo.currentText(), account)

		settings.endGroup()

	# autosave saves the last successful login
	# we don't call it save_login as this function tests the "Save login" checkbox first,
	# while a real save function would not do that
	def autosave_login(self, account: Account) -> None:
		if self.save_login_check.isChecked():
			settings = QSettings()
			settings.beginGroup("Accounts")
			settings.setValue(
				account.account_username, {
					"login": account.account_login,
					"password": base64.b64encode(bytes(account.account_password, "utf-8")),
					"instance": account.account_instance,
					"access_token": account.account_access_token,
					"client_id": account.account_client_id,
					"client_secret": account.account_client_secret,
					"autologin": self.autologin_check.isChecked(),
				})
			settings.endGroup()

	def enable_close_button(self, enabled: bool) -> None:
		self.close_button.setEnabled(enabled)

	# DEBUG: catch == which is probably not desired
	def __eq__(self, other):
		breakpoint()
		return False

	# DEBUG: catch != which is probably not desired
	def __ne__(self, other):
		breakpoint()
		return False
