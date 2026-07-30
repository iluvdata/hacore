"""Tests for REST config_flow.py."""

from http import HTTPStatus
from typing import Any, cast

from aiohttp import ClientError
import pytest

from homeassistant import config_entries
from homeassistant.components.rest import RestConfigEntry
from homeassistant.components.rest.const import CONF_ENCODING, DOMAIN
from homeassistant.const import (
    CONF_AUTHENTICATION,
    CONF_PARAMS,
    CONF_PAYLOAD,
    CONF_TIMEOUT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from .conftest import async_setup_entry

from tests.test_util.aiohttp import AiohttpClientMocker


async def test_create_entry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    get_config_entry_data: dict[str, Any],
) -> None:
    """Test the basic config flow and subentry flow."""
    aioclient_mock.get(
        "http://localhost",
        status=HTTPStatus.OK,
        json={"key": "on"},
        params={"fake_param": "fake_value"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["step_id"] == "user"
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        get_config_entry_data
        | {
            CONF_PAYLOAD: "test payload",
            CONF_PARAMS: [{"key": "fake_param", "value": "fake_value"}],
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    result = hass.config_entries.async_entries(DOMAIN)
    assert len(result) == 1
    entry = cast(RestConfigEntry, result[0])
    assert entry.state == config_entries.ConfigEntryState.LOADED
    rest = entry.runtime_data.rest
    assert rest.last_exception is None
    assert rest.data == '{"key":"on"}'


@pytest.mark.usefixtures("async_mock_resource")
async def test_config_reconfigure_flow(
    hass: HomeAssistant, get_config_entry_data: dict[str, Any]
) -> None:
    """Test config entry reconfigure flow."""
    entry = await async_setup_entry(
        hass,
        get_config_entry_data,
    )
    assert entry.state == config_entries.ConfigEntryState.LOADED
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**get_config_entry_data, CONF_TIMEOUT: 15}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert (
        hass.config_entries.async_get_known_entry(entry.entry_id).data[CONF_TIMEOUT]
        == 15
    )


async def test_invalid_rest_resource(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    get_config_entry_data: dict[str, Any],
) -> None:
    """Test any invalid resource."""
    aioclient_mock.get("http://localhost", exc=ClientError("client error"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        get_config_entry_data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "endpoint_error"}
    assert result["description_placeholders"] == {"error_message": "client error"}


async def test_config_invalid_input(
    hass: HomeAssistant,
    get_config_entry_data: dict[str, Any],
) -> None:
    """Test config entry reconfigure flow."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    user_input = {
        **get_config_entry_data,
        CONF_ENCODING: "fake_encoding",
    }
    user_input[CONF_AUTHENTICATION][CONF_USERNAME] = "test_user"
    with pytest.raises(InvalidData) as ex:
        await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    assert ex.value.schema_errors[CONF_ENCODING] == "codec not found"
    assert ex.value.schema_errors[CONF_AUTHENTICATION] == "credentials_missing"
