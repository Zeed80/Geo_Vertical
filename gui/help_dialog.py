"""
Диалог справки для GeoVertical Analyzer
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTextBrowser,
                             QPushButton, QLineEdit, QLabel, QSplitter)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QTextDocument
import os
from pathlib import Path


class HelpDialog(QDialog):
    """Диалог справки с поиском"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Справка - GeoVertical Analyzer')
        self.setMinimumSize(800, 600)
        self.init_ui()
        self.load_help_content()
    
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Панель поиска
        search_layout = QHBoxLayout()
        search_label = QLabel('Поиск:')
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Введите текст для поиска...')
        self.search_input.textChanged.connect(self.search_text)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # Браузер справки
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        layout.addWidget(self.text_browser)
        
        # Кнопки
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton('Закрыть')
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
    
    def load_help_content(self):
        """Загрузка содержимого справки"""
        content = self.generate_help_content()
        self.text_browser.setHtml(content)
    
    def generate_help_content(self):
        """Генерация HTML содержимого справки"""
        html = """
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
                h2 { color: #34495e; margin-top: 30px; }
                h3 { color: #7f8c8d; margin-top: 20px; }
                p { line-height: 1.6; }
                ul, ol { line-height: 1.8; }
                code { background-color: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
                pre { background-color: #f4f4f4; padding: 10px; border-radius: 5px; overflow-x: auto; }
                .section { margin-bottom: 30px; }
                .highlight { background-color: #fff3cd; padding: 2px 4px; }
            </style>
        </head>
        <body>
            <h1>GeoVertical Analyzer - Руководство пользователя</h1>
            
            <div class="section">
                <h2>1. Быстрый старт</h2>
                <h3>Запуск программы</h3>
                <p><strong>Windows:</strong></p>
                <pre>run.bat</pre>
                <p>или</p>
                <pre>python main.py</pre>
                
                <p><strong>Linux/macOS:</strong></p>
                <pre>./run.sh</pre>
                <p>или</p>
                <pre>python main.py</pre>
                
                <h3>Первые шаги</h3>
                <ol>
                    <li>Запустите программу</li>
                    <li>Нажмите <strong>"📂 Открыть"</strong> или используйте меню <strong>Файл → Открыть</strong></li>
                    <li>Выберите файл с координатами точек (CSV, DXF, GeoJSON и т.д.)</li>
                    <li>Нажмите <strong>"⚙️ Рассчитать"</strong> (или F5)</li>
                    <li>Просмотрите результаты на вкладках "Вертикальность" и "Прямолинейность"</li>
                    <li>Сохраните отчет: <strong>"💾 Сохранить отчет"</strong> (Ctrl+S)</li>
                </ol>
            </div>
            
            <div class="section">
                <h2>2. Работа с данными</h2>
                
                <h3>Поддерживаемые форматы</h3>
                <ul>
                    <li><strong>CSV, TXT</strong> - текстовые координатные файлы</li>
                    <li><strong>Shapefile (SHP)</strong> - геопространственные данные (требует GDAL)</li>
                    <li><strong>GeoJSON</strong> - JSON формат для геоданных</li>
                    <li><strong>DXF</strong> - чертежи AutoCAD</li>
                    <li><strong>Trimble</strong> - JobXML (.jxl), CSV или TXT экспорты</li>
                </ul>
                
                <h3>Формат CSV файлов</h3>
                <p>Минимальный формат:</p>
                <pre>X,Y,Z
10.0,0.0,5.0
7.07,7.07,5.0
...</pre>
                
                <p>Возможные названия колонок:</p>
                <ul>
                    <li>X: x, X, lon, longitude, east, easting</li>
                    <li>Y: y, Y, lat, latitude, north, northing</li>
                    <li>Z: z, Z, h, height, elevation, alt, altitude</li>
                </ul>
                
                <h3>Фильтрация точек</h3>
                <p>Если файл содержит не только точки башни (реперы, точки стояния и т.п.):</p>
                <ol>
                    <li>Нажмите <strong>"🔍 Фильтровать точки"</strong></li>
                    <li>Откроется 3D редактор с интерактивной визуализацией</li>
                    <li>Нажмите <strong>"🔍 Автоматическая фильтрация"</strong></li>
                    <li>Программа автоматически определит и выделит точки башни</li>
                    <li>При необходимости скорректируйте вручную</li>
                    <li>Нажмите <strong>"✓ Применить фильтр"</strong></li>
                </ol>
            </div>
            
            <div class="section">
                <h2>3. Расчеты</h2>
                
                <h3>Выполнение расчета</h3>
                <p>Нажмите <strong>"⚙️ Рассчитать"</strong> (или F5). Программа:</p>
                <ul>
                    <li>Группирует точки по поясам</li>
                    <li>Находит центры поясов</li>
                    <li>Строит ось мачты</li>
                    <li>Вычисляет отклонения</li>
                    <li>Проверяет соответствие нормативам</li>
                </ul>
                
                <h3>Настройка параметров</h3>
                <p>Откройте <strong>Расчет → Параметры расчета</strong> для настройки:</p>
                <ul>
                    <li>Допуск группировки по высоте</li>
                    <li>Метод расчета центра пояса (среднее/МНК)</li>
                    <li>Параметры отображения графиков</li>
                </ul>
                
                <h3>Система координат</h3>
                <p>В панели инструментов выберите систему координат (EPSG). При выборе "Авто" программа попытается определить систему автоматически. Для расчетов данные автоматически преобразуются в метрическую систему.</p>
                
                <p>Популярные системы координат:</p>
                <ul>
                    <li><strong>EPSG:4326</strong> - WGS 84 (GPS, градусы)</li>
                    <li><strong>EPSG:32637</strong> - WGS 84 / UTM zone 37N (Москва)</li>
                    <li><strong>EPSG:28404</strong> - Pulkovo 1942 / Gauss-Kruger zone 4</li>
                </ul>
            </div>
            
            <div class="section">
                <h2>4. Результаты</h2>
                
                <h3>Вкладка "Вертикальность"</h3>
                <ul>
                    <li>График отклонений от вертикали</li>
                    <li>Линии допуска ±0.001·h</li>
                    <li>Цветовая индикация (зеленый - норма, красный - превышение)</li>
                </ul>
                
                <h3>Вкладка "Прямолинейность"</h3>
                <ul>
                    <li>График стрелы прогиба</li>
                    <li>Линия допуска L/750</li>
                    <li>Базовая линия прямолинейности</li>
                </ul>
            </div>
            
            <div class="section">
                <h2>5. Отчеты</h2>
                
                <h3>Сохранение отчета</h3>
                <p>Нажмите <strong>"💾 Сохранить отчет"</strong> или Ctrl+S. Выберите формат:</p>
                <ul>
                    <li><strong>PDF</strong> - профессиональный отчет с графиками (рекомендуется)</li>
                    <li><strong>Word (DOCX)</strong> - редактируемый отчет</li>
                    <li><strong>Excel</strong> - табличные данные для обработки</li>
                </ul>
                
                <h3>PDF отчет включает:</h3>
                <ul>
                    <li>Титульный лист с полной информацией</li>
                    <li>Нормативную базу (СП 70.13330.2012, Инструкция 1980)</li>
                    <li>Исходные данные в табличном виде</li>
                    <li>Результаты расчетов с цветовой индикацией</li>
                    <li>Графики вертикальности и прямолинейности (высокое качество)</li>
                    <li>Выводы и рекомендации по результатам контроля</li>
                </ul>
            </div>
            
            <div class="section">
                <h2>6. Нормативная база</h2>
                
                <h3>СП 70.13330.2012</h3>
                <p><strong>Отклонение от вертикали:</strong></p>
                <pre>d_i ≤ 0.001 × h_i</pre>
                <p>где:</p>
                <ul>
                    <li>d_i - горизонтальное отклонение центра пояса от оси (м)</li>
                    <li>h_i - высота пояса от основания (м)</li>
                </ul>
                
                <h3>Инструкция Минсвязи СССР (1980)</h3>
                <p><strong>Стрела прогиба (прямолинейность):</strong></p>
                <pre>δ_i ≤ L / 750</pre>
                <p>где:</p>
                <ul>
                    <li>δ_i - отклонение от базовой линии прямолинейности (м)</li>
                    <li>L - длина секции между опорными точками (м)</li>
                </ul>
            </div>
            
            <div class="section">
                <h2>7. Горячие клавиши</h2>
                <ul>
                    <li><strong>Ctrl+O</strong> - Открыть файл</li>
                    <li><strong>Ctrl+S</strong> - Сохранить отчет</li>
                    <li><strong>F5</strong> - Выполнить расчет</li>
                    <li><strong>Ctrl+E</strong> - Экспорт схемы</li>
                    <li><strong>F1</strong> - Открыть справку</li>
                </ul>
            </div>
            
            <div class="section">
                <h2>8. Полный пример использования всех функций</h2>
                
                <p>Ниже представлен пошаговый пример работы с программой, демонстрирующий все основные функции:</p>
                
                <h3>Шаг 1: Запуск программы</h3>
                <ol>
                    <li>Запустите программу: <code>run.bat</code> или <code>python main.py</code></li>
                    <li>Откроется главное окно с пустой рабочей областью</li>
                    <li>Ознакомьтесь с интерфейсом: таблица данных, 3D редактор, графики</li>
                </ol>
                
                <h3>Шаг 2: Загрузка данных</h3>
                <ol>
                    <li>Нажмите <strong>"📂 Открыть"</strong> или <strong>Ctrl+O</strong></li>
                    <li>Выберите файл с координатами (например, <code>tower_data.csv</code>)</li>
                    <li>Программа автоматически определит формат и загрузит точки</li>
                    <li>Данные отобразятся в таблице справа</li>
                </ol>
                
                <h3>Шаг 3: Работа с системой координат</h3>
                <ol>
                    <li>В панели инструментов выберите систему координат (EPSG)</li>
                    <li>Если координаты в градусах (GPS), выберите <strong>EPSG:4326</strong></li>
                    <li>Если координаты в метрах (UTM), выберите соответствующую зону, например <strong>EPSG:32637</strong></li>
                    <li>Или выберите <strong>"Авто"</strong> для автоматического определения</li>
                </ol>
                
                <h3>Шаг 4: Фильтрация точек (если нужно)</h3>
                <p><em>Этот шаг необходим, если файл содержит не только точки башни (реперы, точки стояния и т.п.)</em></p>
                <ol>
                    <li>Нажмите <strong>"🔍 Фильтровать точки"</strong></li>
                    <li>Откроется 3D редактор с визуализацией всех точек</li>
                    <li>Нажмите <strong>"🔍 Автоматическая фильтрация"</strong></li>
                    <li>Программа автоматически:
                        <ul>
                            <li>Группирует точки по высоте</li>
                            <li>Анализирует геометрию (определяет точки, образующие окружность)</li>
                            <li>Определяет ось башни</li>
                            <li>Исключает выбросы (реперы, оборудование)</li>
                        </ul>
                    </li>
                    <li>В 3D редакторе:
                        <ul>
                            <li>🟢 <strong>Зеленые точки</strong> - точки башни (выбраны)</li>
                            <li>🔴 <strong>Красные точки</strong> - отклонены (реперы, оборудование)</li>
                        </ul>
                    </li>
                    <li>При необходимости:
                        <ul>
                            <li>Используйте <strong>"🔄 Инвертировать"</strong> для инверсии выбора</li>
                            <li>Используйте <strong>"✏️ Редактировать"</strong> для ручной корректировки</li>
                            <li>Используйте <strong>"➕ Добавить точку"</strong> для добавления пропущенных точек</li>
                        </ul>
                    </li>
                    <li>Нажмите <strong>"✓ Применить фильтр"</strong> для применения изменений</li>
                </ol>
                
                <h3>Шаг 5: Редактирование данных в таблице</h3>
                <ol>
                    <li>Перейдите на вкладку <strong>"Данные"</strong></li>
                    <li>В таблице можно:
                        <ul>
                            <li>Редактировать координаты точек (двойной клик по ячейке)</li>
                            <li>Добавлять новые точки (кнопка <strong>"➕ Добавить строку"</strong>)</li>
                            <li>Удалять точки (выделить строку и нажать <strong>Delete</strong>)</li>
                            <li>Назначать пояса вручную (колонка "Пояс")</li>
                        </ul>
                    </li>
                    <li>Используйте <strong>"Проверить данные"</strong> для валидации</li>
                    <li>Некорректные значения подсвечиваются красным</li>
                </ol>
                
                <h3>Шаг 6: Настройка параметров расчета</h3>
                <ol>
                    <li>Откройте меню <strong>Расчет → Параметры расчета</strong></li>
                    <li>Настройте параметры:
                        <ul>
                            <li><strong>Допуск группировки по высоте:</strong> 0.1 м (по умолчанию)</li>
                            <li><strong>Метод расчета центра пояса:</strong> Среднее или МНК</li>
                            <li><strong>Параметры отображения графиков:</strong> цвета, размеры точек</li>
                        </ul>
                    </li>
                    <li>Нажмите <strong>OK</strong> для сохранения настроек</li>
                </ol>
                
                <h3>Шаг 7: Выполнение расчета</h3>
                <ol>
                    <li>Нажмите <strong>"⚙️ Рассчитать"</strong> или <strong>F5</strong></li>
                    <li>Появится диалог прогресса с индикацией выполнения</li>
                    <li>Программа выполнит:
                        <ul>
                            <li>Группировку точек по поясам с учетом допуска</li>
                            <li>Расчет центров поясов (выбранным методом)</li>
                            <li>Построение оси мачты (линейная аппроксимация)</li>
                            <li>Вычисление горизонтальных отклонений d_i</li>
                            <li>Расчет стрелы прогиба δ_i</li>
                            <li>Проверку соответствия нормативам</li>
                        </ul>
                    </li>
                    <li>После завершения результаты отобразятся автоматически</li>
                </ol>
                
                <h3>Шаг 8: Просмотр результатов</h3>
                
                <h4>Вкладка "Вертикальность":</h4>
                <ol>
                    <li>Перейдите на вкладку <strong>"📈 Вертикальность"</strong></li>
                    <li>Изучите график:
                        <ul>
                            <li>Точки показывают отклонения каждого пояса</li>
                            <li>Зеленые точки - в пределах нормы (d ≤ 0.001·h)</li>
                            <li>Красные точки - превышение допуска</li>
                            <li>Линии ±0.001·h показывают границы допуска</li>
                        </ul>
                    </li>
                    <li>Статистика внизу показывает:
                        <ul>
                            <li>Количество поясов в норме / с превышением</li>
                            <li>Максимальное отклонение</li>
                            <li>Процент соответствия</li>
                        </ul>
                    </li>
                </ol>
                
                <h4>Вкладка "Прямолинейность":</h4>
                <ol>
                    <li>Перейдите на вкладку <strong>"📉 Прямолинейность"</strong></li>
                    <li>Изучите график:
                        <ul>
                            <li>Стрела прогиба относительно базовой линии</li>
                            <li>Линия L/750 показывает допуск прямолинейности</li>
                            <li>Цветовая индикация соответствия</li>
                        </ul>
                    </li>
                </ol>
                
                <h4>Вкладка "Отчет":</h4>
                <ol>
                    <li>Перейдите на вкладку <strong>"📄 Отчет"</strong></li>
                    <li>Просмотрите предпросмотр отчета</li>
                    <li>При необходимости заполните информацию об объекте:
                        <ul>
                            <li>Наименование объекта</li>
                            <li>Местоположение</li>
                            <li>Тип сооружения</li>
                            <li>Организация и исполнитель</li>
                            <li>Примечания</li>
                        </ul>
                    </li>
                </ol>
                
                <h3>Шаг 9: Сохранение отчета</h3>
                <ol>
                    <li>Нажмите <strong>"💾 Сохранить отчет"</strong> или <strong>Ctrl+S</strong></li>
                    <li>Выберите формат отчета:
                        <ul>
                            <li><strong>PDF</strong> - профессиональный отчет с графиками (рекомендуется)</li>
                            <li><strong>Word (DOCX)</strong> - редактируемый отчет</li>
                            <li><strong>Excel</strong> - табличные данные для дальнейшей обработки</li>
                        </ul>
                    </li>
                    <li>Для PDF отчета:
                        <ol>
                            <li>Заполните диалог с информацией об объекте</li>
                            <li>Нажмите <strong>OK</strong></li>
                            <li>Выберите место сохранения</li>
                        </ol>
                    </li>
                    <li>Отчет будет сгенерирован и сохранен</li>
                </ol>
                
                <h3>Шаг 10: Экспорт схемы (опционально)</h3>
                <ol>
                    <li>После выполнения расчетов нажмите <strong>"💾 Сохранить схему"</strong> или <strong>Ctrl+E</strong></li>
                    <li>Выберите формат экспорта:
                        <ul>
                            <li><strong>DXF</strong> - для AutoCAD</li>
                            <li><strong>PDF</strong> - схема в PDF</li>
                        </ul>
                    </li>
                    <li>Настройте параметры экспорта (масштаб, слои)</li>
                    <li>Сохраните схему</li>
                </ol>
                
                <h3>Шаг 11: Дополнительные возможности</h3>
                <ul>
                    <li><strong>Темная тема:</strong> Меню <strong>Вид → Темная тема</strong></li>
                    <li><strong>Пакетная обработка:</strong> Меню <strong>Файл → Открыть несколько файлов...</strong></li>
                    <li><strong>Импорт второй станции:</strong> Для объединения данных с разных станций</li>
                    <li><strong>3D редактор:</strong> Полнофункциональное редактирование точек в 3D пространстве</li>
                    <li><strong>Назначение поясов:</strong> Автоматическое или ручное назначение поясов точкам</li>
                </ul>
                
                <h3>Итоговый результат</h3>
                <p>После выполнения всех шагов вы получите:</p>
                <ul>
                    <li>✅ Полный анализ вертикальности мачты</li>
                    <li>✅ Проверку прямолинейности</li>
                    <li>✅ Визуализацию результатов на графиках</li>
                    <li>✅ Профессиональный отчет в выбранном формате</li>
                    <li>✅ Схему башни (при экспорте)</li>
                </ul>
                
                <p><strong>Примечание:</strong> Все данные сохраняются в проекте. Вы можете вернуться к редактированию в любой момент и пересчитать результаты.</p>
            </div>
            
            <div class="section">
                <h2>9. Решение проблем</h2>
                
                <h3>Python не найден</h3>
                <ol>
                    <li>Установите Python с https://www.python.org/downloads/</li>
                    <li>При установке отметьте "Add Python to PATH"</li>
                    <li>Перезапустите командную строку</li>
                </ol>
                
                <h3>Ошибка установки PyQt6</h3>
                <pre>pip install --upgrade pip setuptools wheel
pip install PyQt6 PyQt6-WebEngine</pre>
                
                <h3>GDAL не устанавливается</h3>
                <p>Используйте программу без поддержки Shapefile (работает с CSV, DXF, GeoJSON). Или используйте Conda для установки GDAL.</p>
            </div>
            
            <div class="section">
                <h2>10. Дополнительная документация</h2>
                <ul>
                    <li><strong>Руководство пользователя:</strong> docs/USER_GUIDE.md</li>
                    <li><strong>Поддержка Trimble:</strong> docs/TRIMBLE_SUPPORT.md</li>
                    <li><strong>Фильтрация точек:</strong> docs/POINT_FILTERING_GUIDE.md</li>
                    <li><strong>Создание отчетов:</strong> docs/HOW_TO_CREATE_REPORT.md</li>
                    <li><strong>История изменений:</strong> CHANGELOG.md</li>
                </ul>
            </div>
            
        </body>
        </html>
        """
        return html
    
    def search_text(self, text):
        """Поиск текста в справке"""
        if not text:
            self.load_help_content()
            return
        
        # Простой поиск - выделение найденного текста
        content = self.text_browser.toHtml()
        if text.lower() in content.lower():
            # Выделяем найденный текст
            highlighted_content = content.replace(
                text, 
                f'<span class="highlight">{text}</span>'
            )
            self.text_browser.setHtml(highlighted_content)
            # Прокручиваем к первому вхождению
            self.text_browser.find(text)

