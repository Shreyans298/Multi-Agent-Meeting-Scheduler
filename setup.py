from setuptools import setup, find_packages

setup(
    name="event_scheduler_multi-agent",
    version="0.1.0",
    description="A multi-agent meeting scheduler using A2A protocol",
    author="Shreyans Jain",
    author_email="jain.shreyans03@gmail.com",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9",
    install_requires=[
        "fastapi",
        "uvicorn",
        "httpx",
        "pydantic",
        "google-auth-oauthlib",
        "google-auth-httplib2",
        "google-api-python-client",
        "pytz"
    ],
)