"""
Retrieval evaluation: a labelled profile -> expected-role set, and the harness
that measures semantic recall and the similarity floor against it.

This package is deliberately outside the test suite. The *arithmetic* is tested
(`tests/test_retrieval_eval.py`), but the numbers themselves depend on the
embedding provider, the network and the catalogue, so they come from running the
harness by hand:

    cd backend
    .\\.venv\\Scripts\\python.exe -m evals.retrieval_eval --provider both

See `evals/retrieval_eval.py` for what is measured and why.
"""
