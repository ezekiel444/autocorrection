"""Correction Engine FastAPI application entry point.

Provides internal API endpoints for text analysis, correction application,
and health checking. Wires all components together.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException

from .config_manager import ConfigManager
from .correction_engine import (
    ConfidenceScorer,
    CorrectionApplier,
    CorrectionPipeline,
    LLMClient,
    OpenAIClient,
    PromptBuilder,
)
from .database import Database
from .dictionary_manager import DictionaryManager
from .language_detector import LanguageDetector
from .models import Correction, CorrectionType, Severity
from .plugin_registry import PluginRegistry
from .schemas import (
    AnalysisRequest,
    ApplyRequest,
    ApplyResponse,
    CorrectionReportSchema,
    CorrectionSchema,
    HealthResponse,
    TextStatisticsSchema,
)
from .style_guide import StyleGuideEnforcer
from .text_segmenter import segment_text

logger = logging.getLogger(__name__)

# ─── Global State ─────────────────────────────────────────────────────────────

config_manager: Optional[ConfigManager] = None
database: Optional[Database] = None
pipeline: Optional[CorrectionPipeline] = None
llm_client: Optional[LLMClient] = None


# ─── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and cleanup resources."""
    global config_manager, database, pipeline, llm_client

    # Load configuration
    config_path = os.environ.get("CONFIG_PATH", "/config/settings.yaml")
    config_manager = ConfigManager(config_path)
    config_manager.load()

    # Initialize database
    db_path = os.environ.get("DATABASE_PATH", "/data/corrections.db")
    database = Database(db_path)
    await database.connect()

    # Initialize LLM client (supports local Ollama or OpenAI)
    llm_backend = os.environ.get("LLM_BACKEND", "ollama")  # "ollama" or "openai"
    llm_base_url = os.environ.get("LLM_BASE_URL", "http://llm:11434")
    llm_timeout = float(os.environ.get("LLM_TIMEOUT", "120"))

    if llm_backend == "openai":
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        openai_base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        llm_client = OpenAIClient(
            api_key=openai_api_key,
            base_url=openai_base_url,
            model=openai_model,
            timeout=30.0,
        )
        logger.info(f"Using OpenAI backend: {openai_model} at {openai_base_url}")
    else:
        llm_client = LLMClient(
            base_url=llm_base_url,
            timeout=llm_timeout,
            max_retries=3,
        )
        logger.info(f"Using local Ollama backend at {llm_base_url}")

    # Initialize components
    model_name = config_manager.get("model.name", "llama3.2:3b")
    temperature = config_manager.get("model.temperature", 0.3)

    language_detector = LanguageDetector(
        default_language=config_manager.get("general.default_language", "en"),
        confidence_threshold=config_manager.get("language.detection_threshold", 0.7),
    )

    dictionary_manager = DictionaryManager()

    # Load dictionaries from configured path
    dict_path = os.environ.get("DICTIONARIES_PATH", "/data/dictionaries")
    _load_dictionaries(dictionary_manager, dict_path)

    # Initialize plugin registry
    plugins_dir = os.environ.get("PLUGINS_PATH", "/plugins")
    plugin_registry = PluginRegistry(
        plugins_dir=plugins_dir,
        max_plugins=config_manager.get("plugins.max_plugins", 50),
        timeout_seconds=config_manager.get("plugins.execution_timeout_seconds", 30),
    )
    plugin_registry.load_plugins()

    # Initialize style guide
    style_rules_path = config_manager.get(
        "style_guide.custom_rules_path", "/config/style_rules.yaml"
    )
    style_guide = StyleGuideEnforcer(
        rules_path=style_rules_path,
        max_sentence_length=config_manager.get("style_guide.max_sentence_length", 30),
        detect_passive_voice=config_manager.get("style_guide.detect_passive_voice", True),
        tone=config_manager.get("style_guide.tone", "neutral"),
    )

    # Initialize confidence scorer
    confidence_scorer = ConfidenceScorer(database=database)

    # Build pipeline
    pipeline = CorrectionPipeline(
        llm_client=llm_client,
        prompt_builder=PromptBuilder(model_name=model_name, temperature=temperature),
        language_detector=language_detector,
        dictionary_manager=dictionary_manager,
        plugin_registry=plugin_registry,
        style_guide=style_guide,
        confidence_scorer=confidence_scorer,
        database=database,
        model_name=model_name,
        temperature=temperature,
    )

    logger.info("Correction Engine initialized successfully")

    yield

    # Cleanup
    if database:
        await database.close()
    logger.info("Correction Engine shut down")


def _load_dictionaries(manager: DictionaryManager, dict_path: str) -> None:
    """Load all dictionaries from the dictionaries directory.

    Args:
        manager: The dictionary manager to load into.
        dict_path: Path to the dictionaries directory.
    """
    import os
    from pathlib import Path

    path = Path(dict_path)
    if not path.exists():
        logger.info(f"Dictionaries path does not exist: {dict_path}")
        return

    for file in path.iterdir():
        if file.suffix == ".txt":
            result = manager.load_from_text(file.stem, str(file))
            if result.success:
                logger.info(
                    f"Loaded dictionary '{file.stem}': "
                    f"{result.terms_loaded} terms, {result.terms_skipped} skipped"
                )
            else:
                logger.warning(f"Failed to load dictionary '{file.stem}': {result.error}")
        elif file.suffix == ".csv":
            result = manager.load_from_csv(file.stem, str(file))
            if result.success:
                logger.info(
                    f"Loaded CSV dictionary '{file.stem}': "
                    f"{result.terms_loaded} terms, {result.terms_skipped} skipped"
                )
            else:
                logger.warning(f"Failed to load dictionary '{file.stem}': {result.error}")


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Correction Engine",
    description="Internal text analysis and correction service",
    version="0.1.0",
    lifespan=lifespan,
)


# ─── Endpoints ────────────────────────────────────────────────────────────────


@app.post("/internal/analyze", response_model=CorrectionReportSchema)
async def analyze_text(request: AnalysisRequest):
    """Analyze text and return a correction report.

    Full pipeline: segment → detect language → LLM → dictionary filter →
    plugins → style guide → score → report.
    """
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    options = request.options
    auto_apply = options.auto_apply_high_confidence if options else False
    style_enabled = options.style_guide_enabled if options else True
    plugins_enabled = options.plugins_enabled if options else True

    report = await pipeline.analyze(
        text=request.text,
        language=request.language,
        auto_apply=auto_apply,
        style_guide_enabled=style_enabled,
        plugins_enabled=plugins_enabled,
    )

    # Convert to response schema
    corrections_schema = [
        CorrectionSchema(
            original_text=c.original_text,
            suggested_text=c.suggested_text,
            correction_type=c.correction_type.value,
            confidence=c.confidence,
            reason=c.reason,
            start_offset=c.start_offset,
            end_offset=c.end_offset,
            severity=c.severity.value,
            rule_name=c.rule_name,
            is_overridden=c.is_overridden,
            confidence_undetermined=c.confidence_undetermined,
            source=c.source,
        )
        for c in report.corrections
    ]

    return CorrectionReportSchema(
        id=report.id,
        timestamp=report.timestamp,
        original_text=report.original_text,
        corrections=corrections_schema,
        language_detected=report.language_detected,
        language_confidence=report.language_confidence,
        text_statistics=TextStatisticsSchema(
            word_count=report.text_statistics.word_count,
            sentence_count=report.text_statistics.sentence_count,
            character_count=report.text_statistics.character_count,
            paragraph_count=report.text_statistics.paragraph_count,
        ),
        metadata=report.metadata,
    )


@app.post("/internal/apply", response_model=ApplyResponse)
async def apply_corrections(request: ApplyRequest):
    """Apply corrections to text.

    Preserves uncorrected segments and handles offset adjustments.
    """
    # Convert schema corrections to model corrections
    corrections = []
    for c in request.corrections:
        try:
            correction_type = CorrectionType(c.correction_type)
        except ValueError:
            correction_type = CorrectionType.GRAMMAR

        try:
            severity = Severity(c.severity)
        except ValueError:
            severity = Severity.WARNING

        corrections.append(
            Correction(
                original_text=c.original_text,
                suggested_text=c.suggested_text,
                correction_type=correction_type,
                confidence=c.confidence,
                reason=c.reason,
                start_offset=c.start_offset,
                end_offset=c.end_offset,
                severity=severity,
                rule_name=c.rule_name,
                is_overridden=c.is_overridden,
                confidence_undetermined=c.confidence_undetermined,
                source=c.source,
            )
        )

    corrected_text = CorrectionApplier.apply_corrections(
        request.text, corrections, request.mode
    )

    return ApplyResponse(corrected_text=corrected_text)


@app.get("/internal/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for Docker and service discovery.

    Returns service status and LLM readiness.
    """
    llm_ready = False
    if llm_client:
        llm_ready = await llm_client.is_healthy()

    status = "healthy" if llm_ready else "degraded"

    return HealthResponse(status=status, llm_ready=llm_ready)
