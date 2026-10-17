import json
from pathlib import Path


def test_default_ethnicity_instruction_is_a_fallback_not_a_hard_rule():
    from novelvideo.generators.prompt_builder import default_ethnicity_instruction

    instruction = default_ethnicity_instruction("Chinese")

    assert "default to Chinese" in instruction
    assert "without identity references" in instruction
    assert "without explicit ethnicity" in instruction
    assert "follow that explicit source" in instruction
    assert "ALL people" not in instruction
    assert "MUST be Chinese" not in instruction
    assert "East Asian" not in instruction


def test_character_default_ethnicity_instruction_allows_explicit_foreign_descriptions():
    from novelvideo.generators.nanobanana_character import _default_ethnicity_instruction

    instruction = _default_ethnicity_instruction("Chinese")

    assert "Default ethnicity for unspecified people: Chinese" in instruction
    assert "only when the character description and reference images do not specify" in instruction
    assert "follow that explicit description" in instruction
    assert "Western" in instruction
    assert "Persian" in instruction
    assert "Do NOT generate Western" not in instruction
    assert "East Asian facial features" not in instruction


def test_prompt_sources_do_not_contain_hard_global_ethnicity_constraints():
    files = [
        Path("src/novelvideo/generators/prompt_builder.py"),
        Path("src/novelvideo/generators/nanobanana_character.py"),
    ]
    forbidden_literals = [
        "East Asian facial features",
        "ALL people in the scene",
        "Do NOT generate Western",
        "Do NOT allow ethnicity drift to Western",
        "mixed-race, or ambiguous ethnicity",
    ]

    for path in files:
        source = path.read_text()
        for literal in forbidden_literals:
            assert literal not in source, f"{path} still contains hard ethnicity constraint {literal!r}"


def test_style_presets_do_not_use_hard_negative_content_constraints():
    preset_dir = Path("src/novelvideo/styles/presets")
    forbidden_negative_phrases = [
        "modern clothing",
        "western architecture",
        "mobile phone",
        "smartphone",
        "business suit",
        "foreign person",
        "western person",
        "childish face",
    ]

    for path in preset_dir.glob("*.json"):
        data = json.loads(path.read_text())
        avoid = data.get("avoid_instructions", "").lower()
        for phrase in forbidden_negative_phrases:
            assert phrase not in avoid, f"{path.name} forbids content phrase {phrase!r}"


def test_removed_spider_verse_style_is_not_used_as_code_default():
    files = [
        Path("src/novelvideo/generators/voxel_restyle.py"),
        Path("src/novelvideo/stage_asset_tasks.py"),
        Path("src/novelvideo/services/style_service.py"),
    ]

    for path in files:
        source = path.read_text()
        assert "spider_verse_mixed_media" not in source, f"{path} still references removed style id"


def test_style_tags_do_not_encode_era_content():
    forbidden_words = {
        "PERIOD",
        "REPUBLICAN",
        "ERA",
        "DYNASTY",
        "MODERN",
        "ANCIENT",
        "DRAMA",
        "FANTASY",
        "民国",
        "古装",
    }

    for path in Path("src/novelvideo/styles/presets").glob("*.json"):
        data = json.loads(path.read_text())
        tag = data["style_tag"].upper()
        normalized = tag.replace(",", " ")
        assert not (set(normalized.split()) & forbidden_words), (
            f"{path.name} style_tag encodes era/content instead of medium/grade: {tag}"
        )


def test_live_action_style_tags_describe_grade_finish():
    expected_tags = {
        "realistic": "NATURAL PHOTOREALISTIC, CLEAN GRADE",
        "chinese_period_drama": "CINEMATIC FILMIC REALISM, WARM SOFT GRADE",
        "republican_era_drama": "VINTAGE FADED FILM, WARM NOSTALGIC GRADE",
        "post_apocalyptic": "DESATURATED GRITTY REALISM, HARSH LIGHT",
        "epic_scifi_live_action": "CINEMATIC PHOTOREALISM, RESTRAINED FILMIC GRADE",
    }
    grade_words = {
        "CLEAN",
        "DESATURATED",
        "FILM",
        "FILMIC",
        "GRADE",
        "GRITTY",
        "HARSH",
        "LIGHT",
        "NATURAL",
        "NOSTALGIC",
        "PHOTOREALISTIC",
        "REALISM",
        "SOFT",
        "VINTAGE",
        "WARM",
    }

    for style_id, expected in expected_tags.items():
        path = Path(f"src/novelvideo/styles/presets/{style_id}.json")
        data = json.loads(path.read_text())
        tag = data["style_tag"]
        assert tag == expected
        normalized_words = set(tag.replace(",", " ").split())
        assert normalized_words & grade_words


def test_guoman_fantasy_preset_contains_only_rendering_style():
    path = Path("src/novelvideo/styles/presets/guoman_fantasy.json")
    data = json.loads(path.read_text())
    instructions = data["style_instructions"]
    lowered = instructions.lower()

    assert "apply this style only to the rendering medium" in lowered
    assert "do not infer or change faces" in lowered
    assert "reference images" in lowered
    assert "do not override them with the style preset" in lowered
    assert "high-status fantasy robes" not in lowered
    assert "black-gold" not in lowered
    assert "when wardrobe is unspecified" not in lowered
    assert "keep the image transparent" not in lowered
    assert data["style_tag"] == "PREMIUM 3D GUOMAN CG"


def test_anime_preset_contains_only_rendering_style():
    path = Path("src/novelvideo/styles/presets/anime.json")
    data = json.loads(path.read_text())
    instructions = data["style_instructions"].lower()

    assert "apply this style only to the rendering medium" in instructions
    assert "do not infer or change facial features" in instructions
    assert "reference images" in instructions
    assert "do not override them with the style preset" in instructions
    assert "eyes: large" not in instructions
    assert "hair: flowing" not in instructions
    assert "watercolor-style environment" not in instructions


def test_post_apocalyptic_preset_does_not_force_human_or_weathered_subjects():
    path = Path("src/novelvideo/styles/presets/post_apocalyptic.json")
    data = json.loads(path.read_text())
    instructions = data["style_instructions"].lower()
    avoid = data["avoid_instructions"].lower()

    assert "real people" not in instructions
    assert "non-human details" in instructions
    assert "only when supported by the character and scene context" in avoid
    assert "must show natural texture and weathering" not in avoid


def test_topic_flavored_presets_defer_to_explicit_story_content():
    preset_ids = [
        "chinese_period_drama",
        "republican_era_drama",
        "post_apocalyptic",
        "epic_scifi_live_action",
        "guoman_fantasy",
    ]

    for style_id in preset_ids:
        path = Path(f"src/novelvideo/styles/presets/{style_id}.json")
        data = json.loads(path.read_text())
        instructions = data["style_instructions"].lower()
        assert (
            "follow the beat, scene, character, and prop descriptions" in instructions
            or "always follow explicit character descriptions" in instructions
        ), f"{style_id} must defer topic flavor to explicit story/entity content"
        assert (
            "do not override" in instructions
            or "over these default style flavors" in instructions
        ), f"{style_id} must prevent default flavor from overriding explicit content"


def test_epic_scifi_preset_is_self_contained_and_preserves_story_content():
    path = Path("src/novelvideo/styles/presets/epic_scifi_live_action.json")
    data = json.loads(path.read_text())

    assert set(data) == {
        "id", "name", "style_instructions", "avoid_instructions",
        "style_tag", "label", "style_family", "animation_subtype",
    }
    assert data["id"] == path.stem
    assert data["style_family"] == "live_action"
    assert data["animation_subtype"] == ""
    assert all(data[key] for key in data if key != "animation_subtype")
    instructions = data["style_instructions"].lower()
    for phrase in (
        "photorealistic live-action", "restrained color grading",
        "grounded physical materials", "monumental composition",
        "when supported by the scene", "when the story calls for science fiction",
        "reference images", "do not override them with the style preset",
        "do not infer a desert setting, a nationality, an era, futuristic props, or a costume",
        "preserve explicit non-human subjects",
    ):
        assert phrase in instructions
    assert "lord of light" not in json.dumps(data).lower()
    assert "dune" not in json.dumps(data).lower()


def test_epic_scifi_preset_has_frontend_option_and_localized_names():
    data = json.loads(Path("src/novelvideo/styles/presets/epic_scifi_live_action.json").read_text())
    options = Path("frontend/src/lib/visual-styles.ts").read_text()
    assert '{ value: "epic_scifi_live_action", labelKey: "ingest.visualStyles.epicScifiLiveAction" }' in options
    for locale, field in (("en", "name"), ("zh", "label")):
        translations = json.loads(Path(f"frontend/public/locales/{locale}/translation.json").read_text())
        assert translations["ingest"]["visualStyles"]["epicScifiLiveAction"] == data[field]


def test_epic_scifi_preset_reaches_prompt_builder_without_inheritance():
    from novelvideo.config import get_style_preset
    from novelvideo.generators.prompt_builder import StyleConfig

    style_id = "epic_scifi_live_action"
    data = json.loads(Path(f"src/novelvideo/styles/presets/{style_id}.json").read_text())
    runtime = get_style_preset(style_id)
    config = StyleConfig(style_name=style_id)

    assert runtime["style_instructions"] == data["style_instructions"]
    assert config.style_keywords == data["style_instructions"]
    assert config.avoid_keywords == data["avoid_instructions"]
    assert config.panel_tag == data["style_tag"]
    assert config.style_family == "live_action"
    assert config.animation_subtype == ""
