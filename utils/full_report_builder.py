"""
Полноценный генератор техотчёта по структуре ДО ТСС.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from core.report_schema import (
    FullReportData,
    Specialist,
    EquipmentEntry,
    DocumentReference,
    VisualInspectionEntry,
    Recommendation,
    Appendix,
    InspectedObject,
    DocumentReviewEntry,
    TechnicalStateEntry,
    ConclusionEntry,
)
from core.services.report_templates import (
    ReportTemplateManager,
    build_report_data_from_template,
)


class FullReportBuilder:
    """Генерирует DOCX-отчёт по полной структуре."""

    def __init__(self, template_manager: ReportTemplateManager | None = None):
        self.template_manager = template_manager or ReportTemplateManager()

    def build_from_template(
        self,
        template_name: str,
        processed_data,
        raw_data,
        output_path: str | Path,
    ) -> Path:
        data = build_report_data_from_template(self.template_manager, template_name, processed_data, raw_data)
        return self.build_docx(data, output_path)

    def build_docx(self, report: FullReportData, output_path: str | Path) -> Path:
        doc = Document()
        self._configure_styles(doc)
        self._configure_document_layout(doc, report)

        self._add_title_page(doc, report)
        self._add_table_of_contents(doc)
        self._add_section_metadata(doc, report)
        self._add_section_object_card(doc, report)
        self._add_section_normatives(doc, report)
        self._add_section_customer(doc, report)
        self._add_section_contractor(doc, report)
        self._add_section_specialists(doc, report.specialists)
        self._add_section_equipment(doc, report.equipment)
        self._add_section_object_list(doc, report.object_list)
        self._add_section_documents(doc, report.documents)
        self._add_section_loads(doc, report)
        self._add_section_structure(doc, report)
        self._add_section_document_review(doc, report.documents_review)
        self._add_section_visual(doc, report.visual_inspection)
        self._add_section_measurements(doc, report)
        self._add_section_protocols(doc, report)
        self._add_section_results(doc, report)
        self._add_section_resource_calc(doc, report)
        self._add_section_technical_state(doc, report.technical_state)
        self._add_section_conclusions(doc, report.conclusions)
        self._add_section_recommendations(doc, report.recommendations)
        self._add_appendices(doc, report.appendices)
        self._add_annex_overview(doc, report)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))
        return output_path

    # --- helpers ---

    def _configure_styles(self, doc: Document) -> None:
        style = doc.styles["Normal"]
        style.font.name = "Arial"
        style.font.size = Pt(10)

    def _configure_document_layout(self, doc: Document, report: FullReportData) -> None:
        section = doc.sections[0]
        
        # Настройка полей страницы: левое 2,0 см, правое 0,75 см
        from docx.shared import Cm
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(0.75)
        
        header = section.header
        header_para = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        header_para.text = f"Технический отчёт\t{report.metadata.project_name}"
        header_para.style = doc.styles["Header"]

        footer = section.footer
        footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        footer_para.text = f"{report.metadata.report_number}\tСтр. "
        self._insert_field_code(footer_para, "PAGE")

    def _insert_field_code(self, paragraph, instruction: str) -> None:
        field = OxmlElement("w:fldSimple")
        field.set(qn("w:instr"), instruction)
        paragraph._p.append(field)

    def _add_title_page(self, doc: Document, report: FullReportData) -> None:
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run("ТЕХНИЧЕСКИЙ ОТЧЕТ")
        run.bold = True
        run.font.size = Pt(18)

        doc.add_paragraph().add_run("\nПО РЕЗУЛЬТАТАМ ДИАГНОСТИЧЕСКОГО ОБСЛЕДОВАНИЯ").bold = True
        doc.add_paragraph(report.metadata.project_name).alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"№ {report.metadata.report_number}").alignment = WD_ALIGN_PARAGRAPH.CENTER

        if report.title_object:
            table = doc.add_table(rows=0, cols=2, style="Table Grid")
            obj = report.title_object
            for label, value in [
                ("Наименование объекта", obj.name),
                ("Инвентарный номер", obj.inventory_number),
                ("Местонахождение", obj.location),
                ("Эксплуатирующая организация", obj.operator),
            ]:
                row = table.add_row().cells
                row[0].text = label
                row[1].text = value

        footer_para = doc.add_paragraph()
        footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer_para.add_run(f"{report.metadata.approval_city}, {report.metadata.approval_date.year} г.")
        doc.add_page_break()

    def _add_table_of_contents(self, doc: Document) -> None:
        doc.add_paragraph("Содержание").style = "Heading 1"
        paragraph = doc.add_paragraph()
        self._insert_field_code(paragraph, 'TOC \\o "1-3" \\h \\z \\u')
        doc.add_page_break()

    def _add_section_metadata(self, doc: Document, report: FullReportData) -> None:
        doc.add_paragraph("1. Основания для проведения работ", style="Heading 1")
        doc.add_paragraph(
            f"Основанием является договор/поручение от {report.metadata.start_date:%d.%m.%Y}."
        )
        doc.add_paragraph("2. Сроки проведения работ", style="Heading 1")
        doc.add_paragraph(
            f"Работы выполнены в период с {report.metadata.start_date:%d.%m.%Y} по {report.metadata.end_date:%d.%m.%Y}."
        )

    def _add_section_object_card(self, doc: Document, report: FullReportData) -> None:
        doc.add_paragraph("Карточка объекта обследования", style="Heading 1")
        if not report.title_object:
            doc.add_paragraph("Карточка объекта не заполнена.")
            return
        obj = report.title_object
        table = doc.add_table(rows=0, cols=2, style="Table Grid")
        for label, value in [
            ("Наименование", obj.name),
            ("Инвентарный номер", obj.inventory_number),
            ("Эксплуатирующая организация", obj.operator),
            ("Местонахождение", obj.location),
            ("Город выпуска", obj.city),
            ("Год составления отчёта", str(obj.year)),
        ]:
            row = table.add_row().cells
            row[0].text = label
            row[1].text = value

    def _add_section_normatives(self, doc: Document, report: FullReportData) -> None:
        doc.add_paragraph("3. Перечень нормативных и правовых актов", style="Heading 1")
        if report.normative_list:
            for norm in report.normative_list:
                doc.add_paragraph(f"• {norm}")
        else:
            doc.add_paragraph("Список нормативных документов будет загружен из шаблона.")

    def _add_section_customer(self, doc: Document, report: FullReportData) -> None:
        doc.add_paragraph("4. Сведения о заказчике", style="Heading 1")
        table = doc.add_table(rows=0, cols=2, style="Table Grid")

        def add_row(label, value):
            row = table.add_row().cells
            row[0].text = label
            row[1].text = value

        add_row("Полное наименование", report.customer.full_name)
        add_row("Руководитель", report.customer.director)
        add_row("Юридический адрес", report.customer.legal_address)
        add_row("Местонахождение", report.customer.actual_address)
        add_row("Телефон", report.customer.phone)
        add_row("E-mail", report.customer.email)

    def _add_section_contractor(self, doc: Document, report: FullReportData) -> None:
        doc.add_paragraph("5. Сведения об организации-исполнителе", style="Heading 1")
        table = doc.add_table(rows=0, cols=2, style="Table Grid")
        entries = [
            ("Полное наименование", report.contractor.full_name),
            ("Руководитель", report.contractor.director),
            ("Юридический адрес", report.contractor.legal_address),
            ("Почтовый адрес", report.contractor.postal_address),
            ("Телефон", report.contractor.phone),
            ("E-mail", report.contractor.email),
            ("Аттестация", report.contractor.accreditation_certificate),
            ("СРО", report.contractor.sro_certificate),
        ]
        for label, value in entries:
            row = table.add_row().cells
            row[0].text = label
            row[1].text = value

    def _add_section_specialists(self, doc: Document, specialists: Iterable[Specialist]) -> None:
        doc.add_paragraph("6. Сведения о специалистах", style="Heading 1")
        table = doc.add_table(rows=1, cols=4, style="Table Grid")
        headers = ["№", "ФИО", "Аттестации", "Срок действия"]
        for idx, header in enumerate(headers):
            table.rows[0].cells[idx].text = header

        for idx, specialist in enumerate(specialists, start=1):
            row = table.add_row().cells
            row[0].text = str(idx)
            row[1].text = specialist.full_name
            row[2].text = "\n".join(f"{k}: {v}" for k, v in specialist.certifications.items())
            row[3].text = "\n".join(f"{k}: {v:%d.%m.%Y}" for k, v in specialist.expires_at.items())

    def _add_section_equipment(self, doc: Document, equipment: Iterable[EquipmentEntry]) -> None:
        doc.add_paragraph("7. Перечень приборов и оборудования", style="Heading 1")
        table = doc.add_table(rows=1, cols=5, style="Table Grid")
        headers = ["№", "Наименование", "Заводской №", "Свидетельство", "Действительно до"]
        for idx, header in enumerate(headers):
            table.rows[0].cells[idx].text = header

        for idx, device in enumerate(equipment, start=1):
            row = table.add_row().cells
            row[0].text = str(idx)
            row[1].text = device.name
            row[2].text = device.serial_number
            row[3].text = device.certificate
            row[4].text = device.valid_until.strftime("%d.%m.%Y")

    def _add_section_documents(self, doc: Document, documents: Iterable[DocumentReference]) -> None:
        doc.add_paragraph("9. Сведения о документах", style="Heading 1")
        for idx, doc_ref in enumerate(documents, start=1):
            line = f"{idx}. {doc_ref.title} — {doc_ref.identifier}"
            if doc_ref.comments:
                line += f" ({doc_ref.comments})"
            doc.add_paragraph(line)

    def _add_section_object_list(self, doc: Document, objects: Iterable[InspectedObject]) -> None:
        doc.add_paragraph("8. Перечень объектов обследования", style="Heading 1")
        items = list(objects)
        if not items:
            doc.add_paragraph("Данные об объектах обследования отсутствуют.")
            return
        table = doc.add_table(rows=1, cols=5, style="Table Grid")
        headers = ["Наименование", "Инвентарный №", "Год ввода", "Местонахождение", "Примечание"]
        for idx, header in enumerate(headers):
            table.rows[0].cells[idx].text = header
        for obj in items:
            row = table.add_row().cells
            row[0].text = obj.name
            row[1].text = obj.inventory_number or ""
            row[2].text = str(obj.commissioning_year or "")
            row[3].text = obj.location or ""
            row[4].text = obj.notes or ""

    def _add_section_loads(self, doc: Document, report: FullReportData) -> None:
        doc.add_paragraph("10. Нагрузки и условия эксплуатации", style="Heading 1")
        if report.loads:
            table = doc.add_table(rows=0, cols=2, style="Table Grid")
            loads = [
                ("Снеговая нагрузка, кПа", f"{report.loads.snow_load_kpa:.2f}"),
                ("Ветровое давление, кПа", f"{report.loads.wind_pressure_kpa:.2f}"),
                ("Толщина гололёда, мм", f"{report.loads.icing_mm:.1f}"),
                ("Сейсмичность, баллы", str(report.loads.seismicity)),
                ("Коэффициент надёжности", f"{report.loads.reliability_factor:.2f}"),
            ]
            for label, value in loads:
                row = table.add_row().cells
                row[0].text = label
                row[1].text = value
        else:
            doc.add_paragraph("Данные по нагрузкам отсутствуют.")

        doc.add_paragraph("10.2. Климатические параметры", style="Heading 2")
        if report.climate:
            cold = report.climate.cold_period.get("text", "")
            warm = report.climate.warm_period.get("text", "")
            doc.add_paragraph(f"Холодный период: {cold}")
            doc.add_paragraph(f"Тёплый период: {warm}")
        else:
            doc.add_paragraph("Климатические параметры не заполнены.")

    def _add_section_structure(self, doc: Document, report: FullReportData) -> None:
        doc.add_paragraph("11. Краткая характеристика и описание конструкций", style="Heading 1")
        if report.structure:
            doc.add_paragraph(report.structure.purpose)
            doc.add_paragraph(report.structure.planning_decisions)
            doc.add_paragraph(report.structure.structural_scheme)
            if report.structure.foundations:
                doc.add_paragraph(report.structure.foundations)
            if report.structure.metal_structure:
                doc.add_paragraph(report.structure.metal_structure)
            if report.structure.geology:
                doc.add_paragraph(report.structure.geology)
            if report.structure.lattice_notes:
                doc.add_paragraph(report.structure.lattice_notes)
        else:
            doc.add_paragraph("Структурная информация отсутствует в шаблоне.")

        if getattr(report, "structural_elements", None):
            doc.add_paragraph("11.1. Элементы решётки и поясов", style="Heading 2")
            table = doc.add_table(rows=1, cols=5, style="Table Grid")
            headers = ["Секция/отметка", "Элемент", "Материал", "Параметры", "Примечание"]
            for idx, header in enumerate(headers):
                table.rows[0].cells[idx].text = header
            for element in report.structural_elements:
                row = table.add_row().cells
                row[0].text = element.section
                row[1].text = element.element
                row[2].text = element.material
                row[3].text = element.parameters
                row[4].text = element.notes or ""

    def _add_section_visual(self, doc: Document, entries: Iterable[VisualInspectionEntry]) -> None:
        doc.add_paragraph("14. Результаты визуального обследования", style="Heading 1")
        table = doc.add_table(rows=1, cols=2, style="Table Grid")
        table.rows[0].cells[0].text = "Конструкция"
        table.rows[0].cells[1].text = "Дефекты"
        for entry in entries:
            row = table.add_row().cells
            row[0].text = entry.element
            row[1].text = entry.defects

    def _add_section_measurements(self, doc: Document, report: FullReportData) -> None:
        doc.add_paragraph("15. Результаты инструментальных измерений", style="Heading 1")
        if not report.measurements:
            doc.add_paragraph("Информация о проведённых измерениях отсутствует.")
            return
        for item in report.measurements:
            doc.add_paragraph(
                f"{item.method} ({item.standard}) — {item.result}"
            )

    def _add_section_document_review(self, doc: Document, entries: Iterable[DocumentReviewEntry]) -> None:
        doc.add_paragraph("13. Результаты анализа технической документации", style="Heading 1")
        items = list(entries)
        if not items:
            doc.add_paragraph("Данные по анализу технической документации отсутствуют.")
            return
        table = doc.add_table(rows=1, cols=4, style="Table Grid")
        headers = ["Документ", "Идентификатор", "Краткий вывод", "Заключение"]
        for idx, header in enumerate(headers):
            table.rows[0].cells[idx].text = header
        for entry in items:
            row = table.add_row().cells
            row[0].text = entry.title
            row[1].text = entry.identifier or ""
            row[2].text = entry.summary or ""
            row[3].text = entry.conclusion or ""

    def _add_section_protocols(self, doc: Document, report: FullReportData) -> None:
        if not any(
            [
                report.angle_measurements,
                report.vertical_deviation_table,
                report.straightness_records,
                report.thickness_measurements,
                report.coating_measurements,
                report.ultrasonic_records,
                report.concrete_strength_records,
                report.protective_layer_records,
                report.vibration_records,
                report.settlement_records,
            ]
        ):
            return
        doc.add_paragraph("16. Протоколы детальных измерений", style="Heading 1")

        if report.angle_measurements:
            self._add_records_table(
                doc,
                "Журнал угловых измерений",
                ["№", "Секция", "Высота, м", "Пояс", "KL", "KR", "KL-KR", "βизм", "Центр", "Δβ", "Δ, мм"],
                [
                    [
                        self._fmt(item.index, 0),
                        item.section,
                        self._fmt(item.height_m),
                        item.belt,
                        self._fmt(item.kl_arcsec),
                        self._fmt(item.kr_arcsec),
                        self._fmt(item.diff_arcsec),
                        self._fmt(item.beta_measured),
                        self._fmt(item.center_value),
                        self._fmt(item.delta_beta),
                        self._fmt(item.delta_mm),
                    ]
                    for item in report.angle_measurements
                ],
            )
        if report.vertical_deviation_table:
            self._add_records_table(
                doc,
                "Отклонения ствола от вертикали",
                ["№ секции", "Отметка, м", "Смещение (предыдущее), мм", "Смещение (текущее), мм"],
                [
                    [
                        self._fmt(item.section_number, 0),
                        self._fmt(item.height_m),
                        self._fmt(item.deviation_previous_mm),
                        self._fmt(item.deviation_current_mm),
                    ]
                    for item in report.vertical_deviation_table
                ],
            )
        if report.straightness_records:
            self._add_records_table(
                doc,
                "Стрелы прогиба поясов",
                ["Пояс №", "Высота, м", "Отклонение, мм", "Допуск, мм"],
                [
                    [
                        self._fmt(item.belt_number, 0),
                        self._fmt(item.height_m),
                        self._fmt(item.deviation_mm),
                        self._fmt(item.tolerance_mm),
                    ]
                    for item in report.straightness_records
                ],
            )
        if report.thickness_measurements:
            self._add_records_table(
                doc,
                "Протокол толщинометрии",
                ["Группа", "Место", "Норматив, мм", "Показания", "Минимум, мм", "Отклонение, %"],
                [
                    [
                        item.group_name,
                        item.location,
                        self._fmt(item.normative_thickness_mm),
                        " / ".join(self._fmt(val) for val in item.readings_mm),
                        self._fmt(item.min_value_mm),
                        self._fmt(item.deviation_percent),
                    ]
                    for item in report.thickness_measurements
                ],
            )
        if report.coating_measurements:
            self._add_records_table(
                doc,
                "Протокол измерения ЛКП",
                ["Группа", "Место", "Мин проект, мкм", "Макс проект, мкм", "Показания", "Минимум, мкм"],
                [
                    [
                        item.group_name,
                        item.location,
                        self._fmt(item.project_range_min_mkm),
                        self._fmt(item.project_range_max_mkm),
                        " / ".join(self._fmt(val) for val in item.readings_mkm),
                        self._fmt(item.min_value_mkm),
                    ]
                    for item in report.coating_measurements
                ],
            )
        if report.ultrasonic_records:
            self._add_records_table(
                doc,
                "Протокол УЗК",
                ["Место", "Sосн, мм", "Sизм, мм", "Экв. площадь", "Глубина", "Длина", "Дефект", "Заключение"],
                [
                    [
                        item.location,
                        self._fmt(item.base_thickness_mm),
                        self._fmt(item.sample_thickness_mm),
                        self._fmt(item.equivalent_area_mm2),
                        self._fmt(item.depth_mm),
                        self._fmt(item.length_mm),
                        item.defect_type or "",
                        item.conclusion,
                    ]
                    for item in report.ultrasonic_records
                ],
            )
        if report.concrete_strength_records:
            self._add_records_table(
                doc,
                "Протокол контроля прочности бетона",
                ["Зона", "Rср, МПа", "R*, МПа"],
                [
                    [item.zone, self._fmt(item.mean_strength_mpa), self._fmt(item.adjusted_strength_mpa)]
                    for item in report.concrete_strength_records
                ],
            )
        if report.protective_layer_records:
            self._add_records_table(
                doc,
                "Протокол защитного слоя бетона",
                ["Место", "Допустимо, мм", "Измерено, мм", "Отклонение, %"],
                [
                    [
                        item.location,
                        self._fmt(item.allowed_mm),
                        self._fmt(item.measured_mm),
                        self._fmt(item.deviation_percent),
                    ]
                    for item in report.protective_layer_records
                ],
            )
        if report.vibration_records:
            self._add_records_table(
                doc,
                "Протокол измерения вибраций",
                ["Место", "Перемещения, мкм", "Частота, Гц"],
                [
                    [
                        item.location,
                        " / ".join(self._fmt(val) for val in item.displacement_microns),
                        self._fmt(item.frequency_hz),
                    ]
                    for item in report.vibration_records
                ],
            )
        if report.settlement_records:
            self._add_records_table(
                doc,
                "Ведомость осадок фундаментов",
                ["Марка", "Год", "Осадка, мм"],
                [
                    [item.mark, self._fmt(item.year, 0), self._fmt(item.settlement_mm)]
                    for item in report.settlement_records
                ],
            )

    def _add_section_results(self, doc: Document, report: FullReportData) -> None:
        doc.add_paragraph("17. Итоги анализа обследования", style="Heading 1")
        if report.residual_resource:
            status = "соответствует" if report.residual_resource.satisfies_requirements else "не соответствует"
            doc.add_paragraph(
                f"Сооружение {status} требованиям прочности. Остаточный ресурс — "
                f"{report.residual_resource.residual_years:.0f} лет."
            )
            if report.residual_resource.notes:
                doc.add_paragraph(report.residual_resource.notes)
        if report.geodesic_results:
            doc.add_paragraph(
                f"Максимальное отклонение по результатам геодезического контроля: "
                f"{report.geodesic_results.get('max_deviation_mm', 0):.1f} мм."
            )

    def _add_section_resource_calc(self, doc: Document, report: FullReportData) -> None:
        if not report.resource_calculation:
            return
        calc = report.resource_calculation
        doc.add_paragraph("18. Расчёт остаточного ресурса", style="Heading 1")
        table = doc.add_table(rows=0, cols=2, style="Table Grid")
        for label, value in [
            ("Фактический срок эксплуатации, лет", self._fmt(calc.service_life_years)),
            ("Постоянная износа λ", self._fmt(calc.wear_constant, 4)),
            ("Полный срок службы, лет", self._fmt(calc.total_service_life_years)),
            ("Остаточный ресурс, лет", self._fmt(calc.residual_resource_years)),
            ("ε (повреждённость)", self._fmt(calc.epsilon, 4)),
            ("λ расчётная", self._fmt(calc.lambda_value, 4)),
        ]:
            row = table.add_row().cells
            row[0].text = label
            row[1].text = value

    def _add_section_technical_state(self, doc: Document, entries: Iterable[TechnicalStateEntry]) -> None:
        doc.add_paragraph("19. Оценка технического состояния конструкций", style="Heading 1")
        items = list(entries)
        if not items:
            doc.add_paragraph("Данные по оценке технического состояния отсутствуют.")
            return
        table = doc.add_table(rows=1, cols=3, style="Table Grid")
        headers = ["Конструкция", "Классификация", "Комментарии"]
        for idx, header in enumerate(headers):
            table.rows[0].cells[idx].text = header
        for entry in items:
            row = table.add_row().cells
            row[0].text = entry.structure
            row[1].text = entry.classification
            row[2].text = entry.comments or ""

    def _add_section_conclusions(self, doc: Document, conclusions: Iterable[ConclusionEntry]) -> None:
        doc.add_paragraph("20. Выводы", style="Heading 1")
        items = list(conclusions)
        if not items:
            doc.add_paragraph("Выводы по результатам обследования не представлены.")
            return
        for idx, conclusion in enumerate(items, start=1):
            doc.add_paragraph(f"{idx}. {conclusion.label}: {conclusion.text}")

    def _add_section_recommendations(self, doc: Document, recs: Iterable[Recommendation]) -> None:
        doc.add_paragraph("21. Рекомендации", style="Heading 1")
        if not recs:
            doc.add_paragraph("Рекомендации не указаны.")
            return
        for idx, rec in enumerate(recs, start=1):
            doc.add_paragraph(f"{idx}. {rec.text}")

    def _add_appendices(self, doc: Document, appendices: Iterable[Appendix]) -> None:
        doc.add_paragraph("Приложения", style="Heading 1")
        for appendix in appendices:
            doc.add_paragraph(f"{appendix.title}: {appendix.description or ''}")
            for file_path in appendix.files:
                doc.add_paragraph(f"• {file_path}")

    def _add_annex_overview(self, doc: Document, report: FullReportData) -> None:
        if not report.annexes:
            return
        doc.add_paragraph("Перечень приложений A–M", style="Heading 1")
        self._add_records_table(
            doc,
            "Сводная таблица приложений",
            ["Код", "Название", "Описание", "Страницы"],
            [
                [annex.code, annex.title, annex.description or "", ", ".join(str(page) for page in annex.pages)]
                for annex in report.annexes
            ],
        )

    def _add_records_table(self, doc: Document, title: str, headers: list[str], rows: list[list[str]]) -> None:
        doc.add_paragraph(title, style="Heading 2")
        if not rows:
            doc.add_paragraph("Нет данных для отображения.")
            return
        table = doc.add_table(rows=1, cols=len(headers), style="Table Grid")
        for idx, header in enumerate(headers):
            table.rows[0].cells[idx].text = header
        for row_values in rows:
            cells = table.add_row().cells
            for idx, value in enumerate(row_values):
                cells[idx].text = value

    @staticmethod
    def _fmt(value, precision: int = 2) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            formatted = f"{value:.{precision}f}"
            return formatted.rstrip("0").rstrip(".")
        return str(value)


__all__ = ["FullReportBuilder"]

