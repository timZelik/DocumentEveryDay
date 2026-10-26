from documenteveryday.captions.arabic_translator import ArabicCaptionTranslator
from documenteveryday.copywriting.clip_copywriter import fallback_copy, normalize_hashtags
from documenteveryday.domain import CaptionCue, ClipPlan, SegmentTag, TranscribedWord, Transcript
from documenteveryday.llm.budget_ledger import BatchBudgetLedger
from documenteveryday.llm.claude_gateway import ClaudeGateway
from documenteveryday.voice.voice_profile import VoiceProfileBuilder, evenly_spaced_excerpt
from tests.fake_claude import FakeClaudeClient, fake_response, json_response


def gateway_answering(respond):
    client = FakeClaudeClient({"": respond})
    return ClaudeGateway(client, "claude-haiku-5-5", 1, BatchBudgetLedger(0.5), lambda decision: None), client


def test_hashtags_are_cleaned_deduplicated_and_capped():
    assert normalize_hashtags(["#Gym", "gym", "meal prep", "", "a", "b", "c", "d", "e"]) == (
        "gym", "mealprep", "a", "b", "c", "d",
    )  # fmt: skip


def test_fallback_copy_uses_my_own_words():
    copy = fallback_copy(ClipPlan(1, 0, 1, 0, 1, tag=SegmentTag.FOOD_PREP), "chicken and rice done for the week")
    assert copy.title == "chicken and rice done for the week" and copy.hashtags == ("foodprep",)


def test_excerpt_samples_across_the_whole_evening():
    words = [f"w{index}" for index in range(10_000)]
    excerpt = evenly_spaced_excerpt(words, maximum_words=600, chunk_words=100)
    assert excerpt.startswith("w0 ") and excerpt.endswith("w9999")
    assert len([word for word in excerpt.split() if word != "..."]) == 600


def test_voice_profile_merges_previous_profile_and_writes_file(tmp_path):
    profile_path = tmp_path / "voice" / "my_voice.md"
    profile_path.parent.mkdir()
    profile_path.write_text("## Openers\n- 'Alright so'")
    gateway, client = gateway_answering(lambda request: fake_response("## Openers\n- 'Alright so'\n- 'Yo'"))
    transcript = Transcript(1, (TranscribedWord("Yo", 0, 0.3), TranscribedWord("guys.", 0.4, 0.8)))
    profile = VoiceProfileBuilder(gateway, profile_path).refresh([transcript])
    assert "'Yo'" in profile and profile_path.read_text().startswith("## Openers")
    assert "Alright so" in client.requests[0]["messages"][0]["content"]


def test_translator_only_pays_once_per_arabic_phrase():
    gateway, client = gateway_answering(
        lambda request: json_response({"translations": [{"cue_index": 1, "english": "How are you"}]})
    )
    translator = ArabicCaptionTranslator(gateway)
    cues = [CaptionCue(0, 1, "I said"), CaptionCue(1, 2, "ازيك", is_arabic=True)]
    first = translator.translate(cues, "I said ازيك", clip_id=1)
    second = translator.translate(cues, "I said ازيك", clip_id=1)
    assert first[1].english_translation == second[1].english_translation == "How are you"
    assert len(client.requests) == 1
