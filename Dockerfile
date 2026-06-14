FROM python:3.12-slim

WORKDIR /srv

# git is needed to pip-install the analytics package from GitHub.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the analytics package in its own layer. CACHEBUST (set by update.sh
# to a timestamp) invalidates only this small --no-deps step, so a rebuild
# always picks up the latest package while the heavy deps above stay cached.
ARG CACHEBUST=0
RUN pip install --no-cache-dir --force-reinstall --no-deps \
    "git+https://github.com/ArnevanDelft/ha-energy-analytics.git"

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
