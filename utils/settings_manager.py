"""
Менеджер настроек приложения
"""

import json
import logging
from typing import Any

from PyQt6.QtCore import QSettings

from core.exceptions import SettingsLoadError, SettingsSaveError

logger = logging.getLogger(__name__)


class SettingsManager:
    """
    Менеджер для управления настройками приложения
    """

    def __init__(self, organization: str = 'GeoVertical', application: str = 'GeoVerticalAnalyzer'):
        """
        Инициализация менеджера настроек

        Args:
            organization: Название организации для QSettings
            application: Название приложения для QSettings
        """
        self.settings = QSettings(organization, application)
        self.organization = organization
        self.application = application

    def save_setting(self, key: str, value: Any) -> None:
        """
        Сохраняет настройку

        Args:
            key: Ключ настройки (может быть вложенным через '/')
            value: Значение настройки
        """
        try:
            self.settings.setValue(key, value)
            self.settings.sync()
            logger.debug(f"Настройка сохранена: {key} = {value}")
        except Exception as e:
            raise SettingsSaveError(f"Ошибка сохранения настройки {key}: {e!s}") from e

    def load_setting(self, key: str, default: Any = None) -> Any:
        """
        Загружает настройку

        Args:
            key: Ключ настройки
            default: Значение по умолчанию

        Returns:
            Значение настройки или default
        """
        try:
            value = self.settings.value(key, default)
            logger.debug(f"Настройка загружена: {key} = {value}")
            return value
        except Exception as e:
            logger.warning(f"Ошибка загрузки настройки {key}: {e}")
            return default

    def save_settings_dict(self, settings_dict: dict[str, Any], prefix: str = '') -> None:
        """
        Сохраняет словарь настроек

        Args:
            settings_dict: Словарь с настройками
            prefix: Префикс для ключей
        """
        try:
            for key, value in settings_dict.items():
                full_key = f"{prefix}/{key}" if prefix else key
                self.save_setting(full_key, value)
            logger.info(f"Сохранено {len(settings_dict)} настроек с префиксом '{prefix}'")
        except Exception as e:
            raise SettingsSaveError(f"Ошибка сохранения словаря настроек: {e!s}") from e

    def load_settings_dict(self, prefix: str = '') -> dict[str, Any]:
        """
        Загружает все настройки с указанным префиксом

        Args:
            prefix: Префикс для ключей

        Returns:
            Словарь с настройками
        """
        try:
            self.settings.beginGroup(prefix)
            keys = self.settings.allKeys()
            result = {}
            for key in keys:
                value = self.settings.value(key)
                result[key] = value
            self.settings.endGroup()
            logger.debug(f"Загружено {len(result)} настроек с префиксом '{prefix}'")
            return result
        except Exception as e:
            logger.warning(f"Ошибка загрузки словаря настроек: {e}")
            return {}

    def export_settings(self, file_path: str) -> None:
        """
        Экспортирует настройки в JSON файл

        Args:
            file_path: Путь для сохранения файла
        """
        try:
            all_keys = self.settings.allKeys()
            settings_dict = {}
            for key in all_keys:
                settings_dict[key] = self.settings.value(key)

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(settings_dict, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"Настройки экспортированы в {file_path}")
        except Exception as e:
            raise SettingsSaveError(f"Ошибка экспорта настроек: {e!s}") from e

    def import_settings(self, file_path: str, merge: bool = True) -> None:
        """
        Импортирует настройки из JSON файла

        Args:
            file_path: Путь к файлу с настройками
            merge: Объединять с существующими настройками (True) или заменять (False)
        """
        try:
            with open(file_path, encoding='utf-8') as f:
                settings_dict = json.load(f)

            if not merge:
                # Очищаем все настройки
                self.settings.clear()

            # Загружаем настройки
            for key, value in settings_dict.items():
                self.save_setting(key, value)

            logger.info(f"Настройки импортированы из {file_path}")
        except Exception as e:
            raise SettingsLoadError(f"Ошибка импорта настроек: {e!s}") from e

    def reset_to_defaults(self) -> None:
        """Сбрасывает все настройки к значениям по умолчанию"""
        try:
            self.settings.clear()
            logger.info("Настройки сброшены к значениям по умолчанию")
        except Exception as e:
            raise SettingsSaveError(f"Ошибка сброса настроек: {e!s}") from e

    # --------------------------------------------------------- Organization defaults

    _ORG_PREFIX = "organization"
    _ORG_KEYS = (
        "full_name", "director", "legal_address", "postal_address",
        "phone", "email", "accreditation_certificate", "sro_certificate",
        "approval_person", "approval_position", "city",
    )

    def save_default_organization(self, data: dict[str, str]) -> None:
        self.save_settings_dict({k: data.get(k, "") for k in self._ORG_KEYS}, prefix=self._ORG_PREFIX)

    def load_default_organization(self) -> dict[str, str]:
        stored = self.load_settings_dict(prefix=self._ORG_PREFIX)
        return {k: str(stored.get(k, "")) for k in self._ORG_KEYS}

