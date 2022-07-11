FROM python:3 as base

ENV PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONUNBUFFERED=1

# Build virtual env
FROM base as builder

ENV PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100 \
  POETRY_VERSION=1.1.12

RUN pip install "poetry==$POETRY_VERSION"
RUN python -m venv /venv
ENV VIRTUAL_ENV="/venv"

WORKDIR /app

COPY poetry.lock pyproject.toml ./

RUN poetry install -n --no-ansi -E torque

COPY . ./

RUN poetry build && /venv/bin/pip install dist/*.whl

# Install into final image
FROM base as final

ENV PATH="/venv/bin:${PATH}"
ENV VIRTUAL_ENV="/venv"

COPY --from=builder /venv /venv

