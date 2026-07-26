from app.services.scoring_service import calculate_score


def make_job(title="Solutions Engineer", location="Remote - LATAM", company_name="Stripe"):
    return {
        "title": title,
        "location": {"name": location},
        "company_name": company_name,
    }


def test_calculate_score_uses_real_candidate_profile_by_default():
    job = make_job(company_name="Stripe")

    score = calculate_score(job)

    assert score > 0


def test_remote_job_keeps_expected_score():
    profile = {"target_companies": []}
    job = make_job(title="Backend Engineer", location="Remote", company_name="Acme")

    score = calculate_score(job, profile=profile)

    assert score == 30


def test_target_company_keeps_20_points():
    profile = {"target_companies": ["Stripe", "Brex", "Ramp", "OpenAI"]}
    job = make_job(title="Backend Engineer", location="New York", company_name="Stripe")

    score = calculate_score(job, profile=profile)

    assert score == 20
