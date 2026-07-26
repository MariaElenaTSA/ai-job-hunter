# --- Job age filter ---
# Default lookback window for /jobs. Convention: 0 or None means "no age limit".
DEFAULT_MAX_AGE_DAYS = 14

# --- Result ranking ---
# Final cap applied to /jobs after scoring and ranking, across all providers combined.
MAX_RESULTS = 20

# --- Content scoring ---
# Points awarded per distinct matched "concept" found in the job description.
# A concept is either a synonym group below or a single term derived from the
# candidate's own profile (tools, skills, responsibilities). See
# scoring_service._build_content_concepts for how duplicates across sources
# (e.g. tool "SQL" vs synonym group "data_analysis") are merged into one concept.
CONTENT_KEYWORD_POINTS = 8
MAX_CONTENT_SCORE = 80

CONTENT_KEYWORD_SYNONYMS = {
    "troubleshooting": ["troubleshoot", "troubleshooting", "root cause", "incident", "debug"],
    "api": ["api", "apis", "rest api", "integration"],
    "data_analysis": ["sql", "data analysis", "analytics", "query"],
    "testing": ["testing", "qa", "test case", "quality assurance"],
    "automation": ["automation", "automate", "workflow"],
    "collaboration": ["cross-functional", "product and engineering", "stakeholder"],
}

# --- Title scoring ---
# The title is a secondary signal: a clear match adds a flat bonus, no match
# adds nothing. It never subtracts points and never disqualifies a job.
TITLE_MATCH_SCORE = 20

TITLE_KEYWORD_SYNONYMS = [
    "solutions engineer",
    "support engineer",
    "implementation engineer",
    "technical account manager",
    "customer success",
    "product operations",
]

# --- Remote modality signals ---
REMOTE_LOCATION_KEYWORDS = ["remote", "anywhere", "distributed"]
ONSITE_LOCATION_KEYWORDS = ["hybrid", "on-site", "onsite", "in-office", "office-based"]

REMOTE_DESCRIPTION_PHRASES = ["fully remote", "remote-first", "work from anywhere"]
ONSITE_DESCRIPTION_PHRASES = [
    "required to work from our office",
    "in the office",
    "on-site requirement",
    "days a week in the office",
    "hybrid schedule",
    "required in the office",
    "required on site",
    "días obligatorios en oficina",
]

# --- Geographic eligibility signals ---
# "Americas" is deliberately excluded from any candidate's acceptable_scopes
# and treated as ambiguous unless the description explicitly confirms Peru/LATAM.
GEO_AMBIGUOUS_SCOPE_WORDS = ["americas"]

# Bare words like "global" or "worldwide" are only trusted when they appear in
# the structured location field. In free-text descriptions we require an
# explicit hiring/eligibility statement to avoid false positives from generic
# marketing language such as "we are a global company".
GEO_ELIGIBLE_DESCRIPTION_PHRASES = [
    "remote worldwide",
    "work from anywhere",
    "candidates located in latin america",
    "candidates based in latin america",
    "open to applicants in peru",
    "open to candidates in peru",
    "hiring in latin america",
]

GEO_US_ONLY_PHRASES = [
    "us only",
    "us-only",
    "usa only",
    "united states only",
    "us applicants only",
    "us residents only",
    "us-based candidates only",
    "must be authorized to work in the us",
    "must be authorized to work in the united states",
]
