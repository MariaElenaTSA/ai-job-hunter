# ai-job-hunter

AI-powered platform that finds high-fit software jobs, scores opportunities, and personalizes resumes automatically.

## Vision

This project aims to help job seekers discover the best opportunities, evaluate their fit, and generate personalized resumes automatically.

## Planned Features

- Opportunity Finder
- Career Fit Scorer
- Resume Personalization
- AI Cover Letter Generator
- Job Application Tracker
- n8n Automation Workflows

## Tech Stack

- Python
- FastAPI
- n8n
- OpenAI
- PostgreSQL
- Docker

## Project Status

🚧 MVP in progress

## Candidate profile setup

The app loads a local profile from `data/candidates/local/profile.json`. This path is ignored by Git so personal profiles and application documents stay on your machine. If the local file is absent (for example, in a fresh clone), the app uses the fictitious schema example at `data/candidates/example/profile.example.json`.

To use your own profile after cloning, create `data/candidates/local/profile.json` using the example file as the schema reference. Keep real CVs and job-specific application documents under `data/candidates/local/applications/`; these files are ignored as well. Do not add personal profile or application files to Git.
