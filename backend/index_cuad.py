from itertools import count
import os

from datasets import load_dataset
from dotenv import load_dotenv

from chatbot import initialize_index, record_text, replace_source

load_dotenv()


def main() -> None:
    initialize_index()
    limit = int(os.getenv("CUAD_LIMIT", "0"))
    dataset = load_dataset("theatticusproject/cuad", streaming=True)
    split = dataset["train"] if hasattr(dataset, "keys") else dataset

    total_chunks = 0
    for index, record in zip(count(), split):
        chunks_indexed = replace_source(f"cuad:{index}", None, record_text(record))
        total_chunks += chunks_indexed
        print(f"Indexed CUAD document {index + 1}: {chunks_indexed} chunks")
        if limit and index + 1 >= limit:
            break

    print(f"Finished. Indexed {index + 1} CUAD documents and {total_chunks} chunks in ChromaDB.")


if __name__ == "__main__":
    main()
