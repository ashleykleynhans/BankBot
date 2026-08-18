"""Tests for LLM backend abstraction layer."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.llm_backend import (
    LLMResponse,
    LLMBackend,
    OpenAIBackend,
    MLXBackend,
    create_backend,
)

# Check if mlx_lm is available (Apple Silicon only)
try:
    import mlx_lm
    HAS_MLX = True
except ImportError:
    HAS_MLX = False

requires_mlx = pytest.mark.skipif(not HAS_MLX, reason="mlx-lm not installed")


def mock_stream_response(text, prompt_tokens=10, generation_tokens=5, generation_tps=25.0):
    """Create a mock mlx_lm GenerationResponse."""
    response = Mock()
    response.text = text
    response.prompt_tokens = prompt_tokens
    response.generation_tokens = generation_tokens
    response.generation_tps = generation_tps
    return response


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_basic_response(self):
        """Test creating a basic response."""
        resp = LLMResponse(content="Hello")
        assert resp.content == "Hello"
        assert resp.prompt_tokens is None
        assert resp.completion_tokens is None
        assert resp.total_tokens is None

    def test_response_with_tokens(self):
        """Test creating a response with token counts."""
        resp = LLMResponse(
            content="Hello",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5
        assert resp.total_tokens == 15


class TestOpenAIBackend:
    """Tests for OpenAIBackend."""

    @patch("openai.OpenAI")
    def test_init(self, mock_openai_cls):
        """Test OpenAI backend initialization."""
        backend = OpenAIBackend(host="localhost", port=1234, model="test-model")
        assert backend.model == "test-model"
        mock_openai_cls.assert_called_once_with(
            base_url="http://localhost:1234/v1",
            api_key="lm-studio",
            timeout=30.0,
        )

    @patch("openai.OpenAI")
    def test_chat_completion(self, mock_openai_cls):
        """Test chat completion returns LLMResponse."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Hello!"))]
        mock_response.usage = Mock(
            prompt_tokens=10, completion_tokens=5, total_tokens=15
        )
        mock_client.chat.completions.create.return_value = mock_response

        backend = OpenAIBackend(host="localhost", port=1234, model="test-model")
        result = backend.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0.5,
            max_tokens=100,
        )

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello!"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5
        assert result.total_tokens == 15

    @patch("openai.OpenAI")
    def test_chat_completion_connection_error_includes_endpoint(self, mock_openai_cls):
        """Test connection failures surface the configured LLM endpoint."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.base_url = "http://myhost:9999/v1"
        mock_client.chat.completions.create.side_effect = Exception(
            "Connection refused"
        )

        backend = OpenAIBackend(host="myhost", port=9999, model="test-model")
        with pytest.raises(ConnectionError, match="http://myhost:9999/v1"):
            backend.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
            )

    @patch("openai.OpenAI")
    def test_chat_completion_no_usage(self, mock_openai_cls):
        """Test chat completion without usage data."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Hello!"))]
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response

        backend = OpenAIBackend(host="localhost", port=1234, model="test-model")
        result = backend.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert result.content == "Hello!"
        assert result.prompt_tokens is None

    @patch("openai.OpenAI")
    def test_chat_completion_with_timeout(self, mock_openai_cls):
        """Test chat completion with custom timeout."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_options_client = MagicMock()
        mock_client.with_options.return_value = mock_options_client
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Hello!"))]
        mock_response.usage = None
        mock_options_client.chat.completions.create.return_value = mock_response

        backend = OpenAIBackend(host="localhost", port=1234, model="test-model")
        result = backend.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            timeout=15.0,
        )

        mock_client.with_options.assert_called_once_with(timeout=15.0)
        assert result.content == "Hello!"

    @patch("openai.OpenAI")
    def test_check_connection_success(self, mock_openai_cls):
        """Test check_connection when server is available."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_model = MagicMock()
        mock_model.id = "test-model"
        mock_client.models.list.return_value = MagicMock(data=[mock_model])

        backend = OpenAIBackend(host="localhost", port=1234, model="test-model")
        assert backend.check_connection() is True

    @patch("openai.OpenAI")
    def test_check_connection_failure(self, mock_openai_cls):
        """Test check_connection when server is unavailable."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.models.list.side_effect = Exception("Connection refused")

        backend = OpenAIBackend(host="localhost", port=1234, model="test-model")
        assert backend.check_connection() is False

    @patch("openai.OpenAI")
    def test_get_available_models(self, mock_openai_cls):
        """Test getting available models."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_model1 = MagicMock()
        mock_model1.id = "model1"
        mock_model2 = MagicMock()
        mock_model2.id = "model2"
        mock_client.models.list.return_value = MagicMock(data=[mock_model1, mock_model2])

        backend = OpenAIBackend(host="localhost", port=1234, model="model1")
        models = backend.get_available_models()

        assert "model1" in models
        assert "model2" in models

    @patch("openai.OpenAI")
    def test_get_available_models_error(self, mock_openai_cls):
        """Test get_available_models on error."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.models.list.side_effect = Exception("Connection refused")

        backend = OpenAIBackend(host="localhost", port=1234, model="model1")
        assert backend.get_available_models() == []


@requires_mlx
class TestMLXBackend:
    """Tests for MLXBackend."""

    def test_import_error(self):
        """Test MLXBackend raises ImportError when mlx_lm is not installed."""
        with patch.dict("sys.modules", {"mlx_lm": None}):
            with pytest.raises(ImportError, match="mlx-lm is required"):
                MLXBackend(model="test-model")

    @patch("mlx_lm.sample_utils.make_sampler")
    @patch("mlx_lm.load")
    @patch("mlx_lm.stream_generate")
    def test_init_loads_model(self, mock_stream_generate, mock_load, mock_make_sampler):
        """Test MLXBackend loads the model on init."""
        mock_model = Mock()
        mock_tokenizer = Mock()
        mock_load.return_value = (mock_model, mock_tokenizer)

        backend = MLXBackend(model="test-model")

        mock_load.assert_called_once_with("test-model")
        assert backend._model is mock_model
        assert backend._tokenizer is mock_tokenizer

    @patch("mlx_lm.sample_utils.make_sampler")
    @patch("mlx_lm.load")
    @patch("mlx_lm.stream_generate")
    def test_chat_completion(self, mock_stream_generate, mock_load, mock_make_sampler):
        """Test MLXBackend chat completion returns real token stats."""
        mock_model = Mock()
        mock_tokenizer = Mock()
        mock_load.return_value = (mock_model, mock_tokenizer)
        mock_tokenizer.apply_chat_template.return_value = "formatted prompt"
        mock_stream_generate.return_value = iter(
            [mock_stream_response("Hello response", prompt_tokens=12, generation_tokens=7, generation_tps=31.4)]
        )
        mock_sampler = Mock()
        mock_make_sampler.return_value = mock_sampler

        backend = MLXBackend(model="test-model")
        result = backend.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0.5,
            max_tokens=100,
        )

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello response"
        assert result.prompt_tokens == 12
        assert result.completion_tokens == 7
        assert result.total_tokens == 19
        assert result.tokens_per_second == 31.4
        mock_tokenizer.apply_chat_template.assert_called_once_with(
            [{"role": "user", "content": "Hi"}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        mock_make_sampler.assert_called_once_with(temp=0.5)
        mock_stream_generate.assert_called_once_with(
            mock_model,
            mock_tokenizer,
            prompt="formatted prompt",
            sampler=mock_sampler,
            max_tokens=100,
        )

    @patch("mlx_lm.sample_utils.make_sampler")
    @patch("mlx_lm.load")
    @patch("mlx_lm.stream_generate")
    def test_chat_completion_accumulates_streamed_text(self, mock_stream_generate, mock_load, mock_make_sampler):
        """Test MLXBackend concatenates text across streamed chunks."""
        mock_load.return_value = (Mock(), Mock())
        mock_stream_generate.return_value = iter(
            [
                mock_stream_response("Hello "),
                mock_stream_response("world", generation_tokens=9),
            ]
        )

        backend = MLXBackend(model="test-model")
        result = backend.chat_completion(messages=[{"role": "user", "content": "Hi"}])

        assert result.content == "Hello world"
        assert result.completion_tokens == 9

    @patch("mlx_lm.sample_utils.make_sampler")
    @patch("mlx_lm.load")
    @patch("mlx_lm.stream_generate")
    def test_chat_completion_strips_thinking_tags(self, mock_stream_generate, mock_load, mock_make_sampler):
        """Test MLXBackend strips thinking tags from response."""
        mock_model = Mock()
        mock_tokenizer = Mock()
        mock_load.return_value = (mock_model, mock_tokenizer)
        mock_tokenizer.apply_chat_template.return_value = "prompt"
        mock_stream_generate.return_value = iter(
            [mock_stream_response("<think>reasoning</think>\nActual answer")]
        )

        backend = MLXBackend(model="test-model")
        result = backend.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert result.content == "Actual answer"

    @patch("mlx_lm.sample_utils.make_sampler")
    @patch("mlx_lm.load")
    @patch("mlx_lm.stream_generate")
    def test_chat_completion_strips_thinking_without_opening_tag(self, mock_stream_generate, mock_load, mock_make_sampler):
        """Test MLXBackend strips thinking content even without opening tag."""
        mock_model = Mock()
        mock_tokenizer = Mock()
        mock_load.return_value = (mock_model, mock_tokenizer)
        mock_tokenizer.apply_chat_template.return_value = "prompt"
        # Model output missing opening  tag
        mock_stream_generate.return_value = iter(
            [mock_stream_response("Some reasoning here" + "</" + "think>" + "Actual answer")]
        )

        backend = MLXBackend(model="test-model")
        result = backend.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert result.content == "Actual answer"

    @patch("mlx_lm.sample_utils.make_sampler")
    @patch("mlx_lm.load")
    @patch("mlx_lm.stream_generate")
    def test_check_connection(self, mock_stream_generate, mock_load, mock_make_sampler):
        """Test MLXBackend check_connection."""
        mock_load.return_value = (Mock(), Mock())

        backend = MLXBackend(model="test-model")
        assert backend.check_connection() is True

    @patch("mlx_lm.sample_utils.make_sampler")
    @patch("mlx_lm.load")
    @patch("mlx_lm.stream_generate")
    def test_get_available_models(self, mock_stream_generate, mock_load, mock_make_sampler):
        """Test MLXBackend get_available_models returns model name."""
        mock_load.return_value = (Mock(), Mock())

        backend = MLXBackend(model="test-model")
        assert backend.get_available_models() == ["test-model"]


class TestCreateBackend:
    """Tests for create_backend factory function."""

    @patch("openai.OpenAI")
    def test_create_openai_backend(self, mock_openai_cls):
        """Test creating an OpenAI backend."""
        config = {
            "llm": {
                "backend": "openai",
                "host": "localhost",
                "port": 1234,
                "model": "test-model",
            }
        }
        backend = create_backend(config)
        assert isinstance(backend, OpenAIBackend)
        assert backend.model == "test-model"

    @requires_mlx
    @patch("mlx_lm.sample_utils.make_sampler")
    @patch("mlx_lm.load")
    @patch("mlx_lm.stream_generate")
    def test_create_mlx_backend(self, mock_stream_generate, mock_load, mock_make_sampler):
        """Test creating an MLX backend."""
        mock_load.return_value = (Mock(), Mock())
        config = {
            "llm": {
                "backend": "mlx",
                "model": "test-model",
            }
        }
        backend = create_backend(config)
        assert isinstance(backend, MLXBackend)

    @requires_mlx
    @patch("mlx_lm.sample_utils.make_sampler")
    @patch("mlx_lm.load")
    @patch("mlx_lm.stream_generate")
    def test_default_backend_is_mlx(self, mock_stream_generate, mock_load, mock_make_sampler):
        """Test default backend type is mlx."""
        mock_load.return_value = (Mock(), Mock())
        config = {"llm": {"model": "test-model"}}
        backend = create_backend(config)
        assert isinstance(backend, MLXBackend)

    @requires_mlx
    @patch("mlx_lm.sample_utils.make_sampler")
    @patch("mlx_lm.load")
    @patch("mlx_lm.stream_generate")
    def test_default_model(self, mock_stream_generate, mock_load, mock_make_sampler):
        """Test default model name."""
        mock_load.return_value = (Mock(), Mock())
        config = {"llm": {}}
        backend = create_backend(config)
        assert isinstance(backend, MLXBackend)
        assert backend.model_name == "mlx-community/GLM-4.7-Flash-4bit"

    def test_unknown_backend_raises(self):
        """Test unknown backend type raises ValueError."""
        config = {"llm": {"backend": "unknown"}}
        with pytest.raises(ValueError, match="Unknown LLM backend"):
            create_backend(config)

    @patch("openai.OpenAI")
    def test_openai_default_host_port(self, mock_openai_cls):
        """Test OpenAI backend uses default host/port if not specified."""
        config = {"llm": {"backend": "openai"}}
        backend = create_backend(config)
        assert isinstance(backend, OpenAIBackend)
        mock_openai_cls.assert_called_once_with(
            base_url="http://localhost:1234/v1",
            api_key="lm-studio",
            timeout=30.0,
        )

    @requires_mlx
    def test_empty_config(self):
        """Test with empty config uses defaults."""
        # This will try mlx backend which requires mlx_lm
        config = {}
        with patch("mlx_lm.load") as mock_load, \
             patch("mlx_lm.stream_generate"), \
             patch("mlx_lm.sample_utils.make_sampler"):
            mock_load.return_value = (Mock(), Mock())
            backend = create_backend(config)
            assert isinstance(backend, MLXBackend)
