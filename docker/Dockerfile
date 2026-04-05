FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /work

RUN pip install --no-cache-dir \
    "pandas>=2.2,<3" \
    "numpy>=2.0,<3" \
    "scikit-learn>=1.4,<1.8" \
    "pyarrow>=17,<22" \
    "tqdm>=4.66,<5"

CMD ["bash"]
