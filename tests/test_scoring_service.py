from app.services.scoring_service import (
    _score_breakdown,
    calculate_geo_eligibility,
    calculate_remote_eligibility,
    calculate_score,
)


def make_job(title="Solutions Engineer", location="Remote - LATAM", company_name="Stripe", content=""):
    return {
        "title": title,
        "location": {"name": location},
        "company_name": company_name,
        "content": content,
    }


FULL_PROFILE = {
    "target_roles": ["Solutions Engineer", "Product Operations"],
    "preferred_responsibilities": ["Investigating complex technical incidents"],
    "skill_names": ["SQL and Data Analysis", "Root Cause Analysis"],
    "tool_names": ["SQL", "Zendesk"],
    "geo_eligibility": {
        "acceptable_scopes": ["Worldwide", "Global", "Latin America", "LATAM", "South America", "Peru"],
    },
}

GIT_TOOL_PROFILE = {
    "target_roles": [],
    "preferred_responsibilities": [],
    "skill_names": [],
    "tool_names": ["Git"],
}

CROSS_FUNCTIONAL_SKILL_PROFILE = {
    "target_roles": [],
    "preferred_responsibilities": [],
    "skill_names": ["Cross-functional Collaboration"],
    "tool_names": [],
}

SECURITY_ENGINEER_FIXTURE_CONTENT = (
    "We conduct penetration testing and red team engagements. "
    "Our team builds custom tooling and automation frameworks, "
    "working cross-functional with every stakeholder across engineering. "
    "You will support incident investigations and root cause analysis. "
    "Strong programming skills in Python are required to test web applications and APIs. "
    "We use big data log analysis tools such as osquery for threat hunting. "
    "Familiarity with AI-assisted development tools such as Claude Code, Cursor "
    "and GitHub Copilot is a plus."
)


# --- calculate_score ---

def test_calculate_score_uses_real_candidate_profile_by_default():
    job = make_job(content="We use SQL and REST API integrations daily.")

    score = calculate_score(job)

    assert score > 0


def test_calculate_score_rewards_content_matches_from_description():
    job = make_job(
        title="Backend Engineer",
        content="You will troubleshoot production incidents, run root cause analysis and query SQL data.",
    )

    score = calculate_score(job, profile=FULL_PROFILE)

    assert score > 0
    assert score <= 80  # no title match: "Backend Engineer" is not in target_roles or title synonyms


def test_calculate_score_title_without_matching_content_is_capped_at_title_score():
    job = make_job(title="Solutions Engineer", content="")

    score = calculate_score(job, profile=FULL_PROFILE)

    assert score == 20


def test_calculate_score_no_title_match_does_not_block_high_content_score():
    job = make_job(
        title="Software Engineer",  # not in target_roles, not a title synonym
        content=(
            "Troubleshoot incidents, root cause analysis, REST API integration, "
            "SQL data analysis, QA testing, workflow automation, cross-functional collaboration."
        ),
    )

    score = calculate_score(job, profile=FULL_PROFILE)

    assert score >= 48  # 6 distinct concepts matched * 8, title contributes 0
    assert score <= 80


def test_calculate_score_does_not_double_count_sql_tool_and_data_analysis_synonym():
    job_with_sql_once = make_job(title="Backend Engineer", content="Strong SQL skills required.")
    job_with_sql_and_synonym = make_job(
        title="Backend Engineer",
        content="Strong SQL skills required. Data analysis experience a plus.",
    )

    score_once = calculate_score(job_with_sql_once, profile=FULL_PROFILE)
    score_with_synonym_too = calculate_score(job_with_sql_and_synonym, profile=FULL_PROFILE)

    assert score_once == 8
    assert score_with_synonym_too == 8  # "sql" and "data analysis" collapse into one concept


def test_calculate_score_ignores_company_name():
    job_stripe = make_job(company_name="Stripe", content="SQL and REST API work.")
    job_other = make_job(company_name="RandomCo", content="SQL and REST API work.")

    assert calculate_score(job_stripe, profile=FULL_PROFILE) == calculate_score(job_other, profile=FULL_PROFILE)


def test_calculate_score_git_tool_does_not_match_inside_github():
    job = make_job(
        title="Backend Engineer",
        content="We use GitHub for source control and code review.",
    )

    score = calculate_score(job, profile=GIT_TOOL_PROFILE)

    assert score == 0


def test_calculate_score_query_synonym_does_not_match_inside_osquery():
    job = make_job(
        title="Backend Engineer",
        content="We rely on osquery for endpoint telemetry.",
    )

    score = calculate_score(job, profile=FULL_PROFILE)

    assert score == 0


def test_calculate_score_merges_root_cause_and_root_cause_analysis_as_one_concept():
    job = make_job(
        title="Backend Engineer",
        content="We investigate root cause analysis after a production incident.",
    )

    score = calculate_score(job, profile=FULL_PROFILE)

    assert score == 8  # "root cause" (synonym) and "root cause analysis" (skill) are one concept


def test_calculate_score_merges_cross_functional_and_cross_functional_collaboration():
    job = make_job(
        title="Backend Engineer",
        content="This role requires strong cross-functional collaboration with other teams.",
    )

    score = calculate_score(job, profile=CROSS_FUNCTIONAL_SKILL_PROFILE)

    assert score == 8  # "cross-functional" (synonym) and the skill name are one concept


def test_calculate_score_still_matches_api_and_apis_as_explicit_plurals():
    job_singular = make_job(title="Backend Engineer", content="Our platform exposes a public API for partners.")
    job_plural = make_job(title="Backend Engineer", content="Our platform exposes public APIs for partners.")

    assert calculate_score(job_singular, profile=FULL_PROFILE) == 8
    assert calculate_score(job_plural, profile=FULL_PROFILE) == 8


def test_calculate_score_treats_hyphen_and_space_as_equivalent_separators():
    job_hyphen = make_job(title="Backend Engineer", content="This role needs strong cross-functional teamwork.")
    job_space = make_job(title="Backend Engineer", content="This role needs strong cross functional teamwork.")

    assert calculate_score(job_hyphen, profile=FULL_PROFILE) == calculate_score(job_space, profile=FULL_PROFILE)
    assert calculate_score(job_space, profile=FULL_PROFILE) == 8


def test_calculate_score_matches_root_cause_analysis_across_hyphen_and_space_variants():
    job = make_job(
        title="Backend Engineer",
        content="We rely on root-cause analysis to resolve production incidents.",
    )

    score = calculate_score(job, profile=FULL_PROFILE)

    assert score == 8  # "root-cause analysis" still matches the "root cause analysis" skill as one concept


def test_calculate_score_security_engineer_fixture_scores_64_not_80():
    job = make_job(
        title="Security Engineer - Offensive Security",
        location="Ireland",
        content=SECURITY_ENGINEER_FIXTURE_CONTENT,
    )

    score = calculate_score(job)  # uses the real candidate profile, like the reported false positive

    assert score == 64


def test_score_breakdown_keeps_title_score_for_solutions_engineer():
    job = make_job(title="Solutions Engineer", content="")

    breakdown = _score_breakdown(job, profile=FULL_PROFILE)

    assert breakdown["title_score"] == 20


def test_score_breakdown_keeps_title_score_for_implementation_engineer():
    job = make_job(title="Implementation Engineer", content="")

    breakdown = _score_breakdown(job, profile=FULL_PROFILE)

    assert breakdown["title_score"] == 20


def test_calculate_score_returns_the_breakdowns_final_score():
    job = make_job(title="Backend Engineer", content="Troubleshoot incidents and analyze APIs.")

    assert calculate_score(job, profile=FULL_PROFILE) == _score_breakdown(job, profile=FULL_PROFILE)["final_score"]


# --- calculate_remote_eligibility ---

def test_remote_eligibility_eligible_for_remote_location():
    job = make_job(location="Remote - LATAM")

    assert calculate_remote_eligibility(job) == "eligible"


def test_remote_eligibility_not_eligible_when_description_requires_office_presence():
    job = make_job(
        location="Lima, Peru",
        content="Employees are required to work from our office five days a week.",
    )

    assert calculate_remote_eligibility(job) == "not_eligible"


def test_remote_eligibility_ambiguous_when_metadata_and_description_conflict():
    job = make_job(
        location="Remote (US)",
        content="Employees are required to work from our office 2 days a week in the office.",
    )

    assert calculate_remote_eligibility(job) == "ambiguous"


def test_remote_eligibility_not_eligible_for_hybrid_location():
    job = make_job(location="Hybrid - New York")

    assert calculate_remote_eligibility(job) == "not_eligible"


def test_remote_eligibility_ambiguous_when_no_modality_signal_at_all():
    job = make_job(location="New York", content="")

    assert calculate_remote_eligibility(job) == "ambiguous"


# --- calculate_geo_eligibility ---

def test_geo_eligibility_eligible_for_worldwide_location():
    job = make_job(location="Remote - Worldwide")

    assert calculate_geo_eligibility(job, profile=FULL_PROFILE) == "eligible"


def test_geo_eligibility_eligible_for_latam_location():
    job = make_job(location="Remote - LATAM")

    assert calculate_geo_eligibility(job, profile=FULL_PROFILE) == "eligible"


def test_geo_eligibility_eligible_for_onsite_peru_location():
    job = make_job(location="Lima, Peru")

    assert calculate_geo_eligibility(job, profile=FULL_PROFILE) == "eligible"


def test_geo_eligibility_not_eligible_for_stripe_style_us_only_locations():
    job = make_job(
        location="US-Remote, US-San Francisco, US-Chicago, US-New York, US-Seattle, US-Texas"
    )

    assert calculate_remote_eligibility(job) == "eligible"
    assert calculate_geo_eligibility(job, profile=FULL_PROFILE) == "not_eligible"


def test_geo_eligibility_not_eligible_for_explicit_us_only_location():
    job = make_job(location="Remote - US Only")

    assert calculate_geo_eligibility(job, profile=FULL_PROFILE) == "not_eligible"


def test_geo_eligibility_ambiguous_for_americas_without_confirmation():
    job = make_job(location="Remote - Americas")

    assert calculate_geo_eligibility(job, profile=FULL_PROFILE) == "ambiguous"


def test_geo_eligibility_does_not_treat_generic_global_language_as_eligible():
    job = make_job(
        location="New York",
        content="We are a global company with a global team and an international organization culture.",
    )

    assert calculate_geo_eligibility(job, profile=FULL_PROFILE) != "eligible"
