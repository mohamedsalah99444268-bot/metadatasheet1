"""Emit classified ordering sections as evidence-linked parsed fields."""

from .base import BaseParser, ParseContext, ParsedFieldResult


class OrderingSectionParser(BaseParser):
    def parse(self, context: ParseContext) -> list[ParsedFieldResult]:
        results: list[ParsedFieldResult] = []
        for section in context.sections_of_type("ordering"):
            results.append(ParsedFieldResult(
                field_type="ordering_section",
                value=section.title,
                confidence=0.85,
                parser_rule=section.classifier_rule,
                page_number=section.page_number,
                source_text=section.source_text,
                x0=section.x0, y0=section.y0, x1=section.x1, y1=section.y1,
                section_name="Ordering Information",
            ))

        return results
