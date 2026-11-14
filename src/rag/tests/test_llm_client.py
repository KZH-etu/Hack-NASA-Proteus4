import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.rag.llm_client import LMStudioClient


def _make_chat_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _make_embed_response(items: list[tuple[int, list[float]]]) -> SimpleNamespace:
    return SimpleNamespace(
        data=[SimpleNamespace(index=idx, embedding=vec) for idx, vec in items]
    )


class TestLMStudioClient(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_openai = MagicMock()
        self.client = LMStudioClient(
            base_url="http://localhost:1234/v1",
            api_key="lm-studio",
            metadata_model="phi-3.5-mini-instruct",
            embedding_model="qwen3-embedding-0.6b",
            embedding_batch_size=32,
            client=self.mock_openai,
        )

    def test_check_connection_success(self) -> None:
        self.mock_openai.models.list.return_value = SimpleNamespace(data=[])
        self.client.check_connection()
        self.mock_openai.models.list.assert_called_once()

    def test_check_connection_failure_raises_connection_error(self) -> None:
        self.mock_openai.models.list.side_effect = RuntimeError("Connection refused")
        with self.assertRaises(ConnectionError):
            self.client.check_connection()

    def test_extract_metadata_pure_json(self) -> None:
        self.mock_openai.chat.completions.create.return_value = _make_chat_response(
            '{"mission_program": "Apollo", "experiment_year": 1971, "authors": "J. Doe, A. Smith"}'
        )
        meta = self.client.extract_metadata_json("# Apollo Fire Safety Report")
        self.assertEqual(meta.mission_program, "Apollo")
        self.assertEqual(meta.experiment_year, 1971)
        self.assertEqual(meta.authors, "J. Doe, A. Smith")

    def test_extract_metadata_strips_markdown_code_fences(self) -> None:
        self.mock_openai.chat.completions.create.return_value = _make_chat_response(
            '```json\n{"mission_program": "Skylab", "experiment_year": 1973, "authors": "R. Roe"}\n```'
        )
        meta = self.client.extract_metadata_json("Skylab text")
        self.assertEqual(meta.mission_program, "Skylab")
        self.assertEqual(meta.experiment_year, 1973)
        self.assertEqual(meta.authors, "R. Roe")

    def test_extract_metadata_handles_surrounding_text(self) -> None:
        self.mock_openai.chat.completions.create.return_value = _make_chat_response(
            'Here is the extracted JSON:\n{"mission_program": "ISS", "experiment_year": 2019, "authors": "M. Curie"}\nHope this helps!'
        )
        meta = self.client.extract_metadata_json("ISS experiment")
        self.assertEqual(meta.mission_program, "ISS")
        self.assertEqual(meta.experiment_year, 2019)

    def test_extract_metadata_handles_null_or_string_year(self) -> None:
        self.mock_openai.chat.completions.create.return_value = _make_chat_response(
            '{"mission_program": "Shuttle", "experiment_year": "1995", "authors": "Dr. Lee"}'
        )
        meta1 = self.client.extract_metadata_json("Shuttle")
        self.assertEqual(meta1.experiment_year, 1995)

        self.mock_openai.chat.completions.create.return_value = _make_chat_response(
            '{"mission_program": "Shuttle", "experiment_year": null, "authors": "Dr. Lee"}'
        )
        meta2 = self.client.extract_metadata_json("Shuttle")
        self.assertIsNone(meta2.experiment_year)

    def test_extract_metadata_normalizes_authors_list_to_string(self) -> None:
        self.mock_openai.chat.completions.create.return_value = _make_chat_response(
            '{"mission_program": "ISS", "experiment_year": 2022, "authors": ["Alice", "Bob"]}'
        )
        meta = self.client.extract_metadata_json("ISS")
        self.assertEqual(meta.authors, "Alice, Bob")

    def test_extract_metadata_invalid_json_raises_value_error(self) -> None:
        self.mock_openai.chat.completions.create.return_value = _make_chat_response(
            "I cannot parse this document."
        )
        with self.assertRaises(ValueError):
            self.client.extract_metadata_json("bad")

    def test_embed_texts_batches_and_preserves_order(self) -> None:
        texts = [f"chunk {i}" for i in range(65)]

        def fake_create(model: str, input: list[str]) -> SimpleNamespace:
            # Return reversed order within each batch to verify index sorting
            items = [
                (idx, [float(idx), float(len(txt))])
                for idx, txt in reversed(list(enumerate(input)))
            ]
            return _make_embed_response(items)

        self.mock_openai.embeddings.create.side_effect = fake_create
        vectors = self.client.embed_texts(texts)

        self.assertEqual(self.mock_openai.embeddings.create.call_count, 3)
        call_sizes = [
            len(call.kwargs["input"])
            for call in self.mock_openai.embeddings.create.call_args_list
        ]
        self.assertEqual(call_sizes, [32, 32, 1])
        self.assertEqual(len(vectors), 65)
        self.assertEqual(vectors[0], [0.0, float(len("chunk 0"))])
        self.assertEqual(vectors[64], [0.0, float(len("chunk 64"))])

    def test_embed_texts_empty_input_makes_no_api_call(self) -> None:
        self.assertEqual(self.client.embed_texts([]), [])
        self.mock_openai.embeddings.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
