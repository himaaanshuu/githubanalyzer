"""
Evidence system for grounding analysis claims in repository data.

Every important insight is backed by specific file paths and line numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass
class Evidence:
    claim: str
    sources: list[str] = field(default_factory=list)  # e.g., ["src/auth.ts:42", "src/middleware.ts:15"]
    confidence: Confidence = Confidence.MEDIUM
    category: str = "general"  # architecture, security, performance, pattern, etc.

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "evidence": self.sources,
            "confidence": self.confidence.value,
            "category": self.category,
        }


@dataclass
class AnalysisMetrics:
    files_analyzed: int = 0
    files_with_errors: int = 0
    parse_success_rate: float = 0.0
    total_symbols: int = 0
    total_functions: int = 0
    total_classes: int = 0
    total_methods: int = 0
    total_imports: int = 0
    total_exports: int = 0
    total_calls: int = 0
    imports_resolved: int = 0
    imports_unresolved: int = 0
    calls_resolved: int = 0
    calls_unresolved: int = 0
    cross_file_references: int = 0
    framework_confidence: float = 0.0
    architecture_confidence: float = 0.0
    languages_detected: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "files_analyzed": self.files_analyzed,
            "files_with_errors": self.files_with_errors,
            "parse_success_rate": self.parse_success_rate,
            "total_symbols": self.total_symbols,
            "total_functions": self.total_functions,
            "total_classes": self.total_classes,
            "total_methods": self.total_methods,
            "total_imports": self.total_imports,
            "total_exports": self.total_exports,
            "total_calls": self.total_calls,
            "imports_resolved": self.imports_resolved,
            "imports_unresolved": self.imports_unresolved,
            "calls_resolved": self.calls_resolved,
            "calls_unresolved": self.calls_unresolved,
            "cross_file_references": self.cross_file_references,
            "framework_confidence": self.framework_confidence,
            "architecture_confidence": self.architecture_confidence,
            "languages_detected": self.languages_detected,
        }


class EvidenceStore:
    """Collects and organizes evidence for analysis claims."""

    def __init__(self):
        self.evidence: list[Evidence] = []
        self.metrics = AnalysisMetrics()

    def add(self, claim: str, sources: list[str], confidence: Confidence = Confidence.MEDIUM, category: str = "general"):
        self.evidence.append(Evidence(
            claim=claim,
            sources=sources,
            confidence=confidence,
            category=category,
        ))

    def add_high(self, claim: str, sources: list[str], category: str = "general"):
        self.add(claim, sources, Confidence.HIGH, category)

    def add_medium(self, claim: str, sources: list[str], category: str = "general"):
        self.add(claim, sources, Confidence.MEDIUM, category)

    def add_low(self, claim: str, sources: list[str], category: str = "general"):
        self.add(claim, sources, Confidence.LOW, category)

    def get_by_category(self, category: str) -> list[Evidence]:
        return [e for e in self.evidence if e.category == category]

    def get_high_confidence(self) -> list[Evidence]:
        return [e for e in self.evidence if e.confidence == Confidence.HIGH]

    def to_dict(self) -> dict:
        return {
            "evidence": [e.to_dict() for e in self.evidence],
            "metrics": self.metrics.to_dict(),
        }

    def summary(self) -> str:
        """Human-readable summary of evidence."""
        lines = []
        by_category = {}
        for e in self.evidence:
            by_category.setdefault(e.category, []).append(e)

        for cat, items in sorted(by_category.items()):
            lines.append(f"\n## {cat.replace('_', ' ').title()} ({len(items)} claims)")
            for item in items:
                sources = ", ".join(item.sources[:3])
                if len(item.sources) > 3:
                    sources += f" +{len(item.sources) - 3} more"
                lines.append(f"- [{item.confidence.value}] {item.claim} ({sources})")

        return "\n".join(lines)
