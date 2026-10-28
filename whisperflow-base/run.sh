#!/bin/bash

abort()
{
    echo "*** FAILED ***" >&2
    exit 1
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

cd "$SCRIPT_DIR"

if [ "$#" -eq 0 ]; then
    echo "No arguments provided. Usage: 
    1. '-local' to build local environment
    2. '-docker' to build and run docker container
    3. '-test' to run linter, formatter and tests
    4. '-benchmark' to run benchmark tests
    5. '-run-server' to run fastapi server
    6. '-setup' to run package setup"
elif [ $1 = "-local" ]; then
    trap 'abort' 0
    set -e
    echo "Running format, linter and tests"
    rm -rf "$VENV_DIR"

    PYTHON_CMD="python3"
    if command -v python3.12 >/dev/null 2>&1; then
        PYTHON_CMD="python3.12"
    fi

    $PYTHON_CMD -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip wheel
    pip install "setuptools<70"
    pip install -r ./requirements-dev.txt

    black whisperflow tests
    pylint --fail-under=9.9 whisperflow tests
    pytest --ignore=tests/benchmark --cov-fail-under=95 --cov whisperflow -v tests
elif [ $1 = "-test" ]; then
    trap 'abort' 0
    set -e
    
    echo "Running format, linter and tests"
    source "$VENV_DIR/bin/activate"
    black whisperflow tests
    pylint --fail-under=9.9 whisperflow tests
    pytest --ignore=tests/benchmark --cov-fail-under=95 --cov --log-cli-level=INFO whisperflow -v tests
elif [ $1 = "-docker" ]; then
    echo "Building and running docker image"
    docker stop whisperflow-container
    docker rm whisperflow-container
    docker rmi whisperflow-image
    docker build --tag whisperflow-image --build-arg CACHEBUST=$(date +%s) . --file Dockerfile.test
    docker run --name whisperflow-container -p 8888:8888 -d whisperflow-image
elif [ $1 = "-benchmark" ]; then
    echo "Running WhisperFlow Server"
    source "$VENV_DIR/bin/activate"
    kill $(lsof -t -i:8181) 
    nohup uvicorn whisperflow.fast_server:app --host 0.0.0.0 --port 8181 &
    sleep 2s
    echo "Running WhisperFlow benchmark tests"
    pytest -v -s tests/benchmark
    kill $(lsof -t -i:8181)
elif [ $1 = "-run-server" ]; then
    echo "Running WhisperFlow server"
    source "$VENV_DIR/bin/activate"
    kill $(lsof -t -i:8181) 2>/dev/null || true
    uvicorn whisperflow.fast_server:app --host 0.0.0.0 --port 8181
elif [ $1 = "-test-package" ]; then
    echo "Running WhisperFlow package setup"
    python setup.py sdist bdist_wheel
    rm -rf .venv_test
    python3 -m venv .venv_test
    source .venv_test/bin/activate
    VERSION=$(python -c "import whisperflow; print(whisperflow.__version__)")
    pip install ./dist/whisperflow-$VERSION-py3-none-any.whl
    pytest --ignore=tests/benchmark --cov-fail-under=95 --cov whisperflow -v tests
else
  echo "Wrong argument is provided. Usage:
    1. '-local' to build local environment
    2. '-docker' to build and run docker container
    3. '-test' to run linter, formatter and tests
    4. '-benchmark' to run benchmark tests
    5. '-run-server' to run fastapi server
    6. '-setup' to run package setup"
fi

trap : 0
echo >&2 '*** DONE ***'
