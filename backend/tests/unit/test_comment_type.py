"""Unit tests for classify_comment_type — pure function, no DB needed."""
import pytest

from app.services.github_sync import classify_comment_type


class TestClassifyCommentType:
    # --- Nit ---

    def test_nit_prefix_colon(self):
        assert classify_comment_type("nit: rename this variable") == "nit"

    def test_nit_prefix_space(self):
        assert classify_comment_type("nit use camelCase here") == "nit"

    def test_nitpick_prefix(self):
        assert classify_comment_type("nitpick: trailing whitespace") == "nit"

    def test_optional_prefix(self):
        assert classify_comment_type("optional: could simplify this") == "nit"

    def test_minor_prefix(self):
        assert classify_comment_type("minor: typo in comment") == "nit"

    def test_style_prefix(self):
        assert classify_comment_type("style: prefer single quotes") == "nit"

    def test_cosmetic_prefix(self):
        assert classify_comment_type("cosmetic: alignment") == "nit"

    def test_tiny_prefix(self):
        assert classify_comment_type("tiny: extra space") == "nit"

    # --- Blocker ---

    def test_blocker_prefix(self):
        assert classify_comment_type("blocker: this breaks auth") == "blocker"

    def test_blocking_prefix(self):
        assert classify_comment_type("blocking: missing null check") == "blocker"

    def test_must_fix_prefix(self):
        assert classify_comment_type("must fix: SQL injection risk") == "blocker"

    def test_critical_prefix(self):
        assert classify_comment_type("critical: data corruption possible") == "blocker"

    def test_bug_prefix(self):
        assert classify_comment_type("bug: off-by-one error here") == "blocker"

    def test_security_issue_content(self):
        assert classify_comment_type("This has a security issue with user input") == "blocker"

    def test_race_condition_content(self):
        assert classify_comment_type("There's a race condition between these two calls") == "blocker"

    def test_data_loss_content(self):
        assert classify_comment_type("This could lead to data loss if interrupted") == "blocker"

    def test_will_break_content(self):
        assert classify_comment_type("This will break on null input") == "blocker"

    def test_memory_leak_content(self):
        assert classify_comment_type("This creates a memory leak") == "blocker"

    # --- Suggestion ---

    def test_suggestion_prefix(self):
        assert classify_comment_type("suggestion: use a map here instead") == "suggestion"

    def test_consider_prefix(self):
        assert classify_comment_type("consider: extracting this to a helper") == "suggestion"

    def test_github_suggestion_block(self):
        assert classify_comment_type("Try this:\n```suggestion\nconst x = 1;\n```") == "suggestion"

    def test_have_you_considered(self):
        assert classify_comment_type("have you considered using a set?") == "suggestion"

    def test_what_about(self):
        assert classify_comment_type("what about using async here?") == "suggestion"

    def test_alternatively(self):
        assert classify_comment_type("alternatively, we could use a queue") == "suggestion"

    def test_perhaps(self):
        assert classify_comment_type("perhaps a different approach would work") == "suggestion"

    # --- Architectural ---

    def test_architecture_keyword(self):
        assert classify_comment_type("This affects the architecture of the module") == "architectural"

    def test_design_concern(self):
        assert classify_comment_type("I have a design concern about this approach") == "architectural"

    def test_coupling_keyword(self):
        assert classify_comment_type("This introduces tight coupling between services") == "architectural"

    def test_separation_of_concern(self):
        assert classify_comment_type("This violates separation of concern") == "architectural"

    def test_abstraction_keyword(self):
        assert classify_comment_type("The abstraction level seems wrong here") == "architectural"

    def test_single_responsibility(self):
        assert classify_comment_type("This class breaks single responsibility") == "architectural"

    def test_encapsulation_keyword(self):
        assert classify_comment_type("This breaks encapsulation of the internal state") == "architectural"

    def test_dependency_injection(self):
        assert classify_comment_type("Should use dependency injection here") == "architectural"

    # --- Praise ---

    def test_lgtm(self):
        assert classify_comment_type("LGTM") == "praise"

    def test_looks_good(self):
        assert classify_comment_type("Looks good to me!") == "praise"

    def test_nice_catch(self):
        assert classify_comment_type("Nice catch on the edge case") == "praise"

    def test_good_call(self):
        assert classify_comment_type("good call, much cleaner now") == "praise"

    def test_awesome(self):
        assert classify_comment_type("This is awesome work") == "praise"

    def test_excellent(self):
        assert classify_comment_type("Excellent refactoring") == "praise"

    def test_well_done(self):
        assert classify_comment_type("well done on this fix") == "praise"

    def test_thumbs_up_emoji(self):
        assert classify_comment_type("\U0001f44d") == "praise"

    def test_nice_prefix(self):
        assert classify_comment_type("Nice, this is clean") == "praise"

    def test_great_prefix(self):
        assert classify_comment_type("Great improvement") == "praise"

    # --- Question ---

    def test_question_prefix(self):
        assert classify_comment_type("question: why not use a hashmap?") == "question"

    def test_ends_with_question_mark(self):
        assert classify_comment_type("Should we handle the error case here?") == "question"

    def test_why_prefix(self):
        assert classify_comment_type("why is this needed?") == "question"

    def test_what_prefix(self):
        assert classify_comment_type("what happens if this is null?") == "question"

    def test_how_prefix(self):
        assert classify_comment_type("how does this handle concurrency?") == "question"

    def test_wondering(self):
        assert classify_comment_type("wondering if we need both checks") == "question"

    def test_curious(self):
        assert classify_comment_type("curious about the performance impact") == "question"

    # --- General ---

    def test_general_plain_comment(self):
        assert classify_comment_type("Updated the variable name.") == "general"

    def test_general_empty_string(self):
        assert classify_comment_type("") == "general"

    def test_general_none_body(self):
        # The caller passes "" for None bodies, but test robustness
        assert classify_comment_type("") == "general"

    def test_general_ambiguous(self):
        assert classify_comment_type("I changed this in the last commit.") == "general"

    # --- Priority ordering ---

    def test_nit_beats_question(self):
        # "nit: why?" should be nit, not question
        assert classify_comment_type("nit: why is this here?") == "nit"

    def test_blocker_prefix_beats_question(self):
        assert classify_comment_type("blocker: did you test this?") == "blocker"

    def test_suggestion_prefix_beats_question(self):
        assert classify_comment_type("suggestion: maybe try a different approach?") == "suggestion"

    def test_blocker_content_beats_question(self):
        assert classify_comment_type("will break if called twice?") == "blocker"

    def test_case_insensitive(self):
        assert classify_comment_type("NIT: fix spacing") == "nit"
        assert classify_comment_type("BLOCKER: must fix") == "blocker"
        assert classify_comment_type("LGTM!") == "praise"
