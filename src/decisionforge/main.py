import uvicorn


def run() -> None:
    uvicorn.run("decisionforge.api:app", host="127.0.0.1", port=8014, reload=False)


if __name__ == "__main__":
    run()
