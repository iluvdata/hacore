"""Fixtures for REST component tests."""

from typing import Any

from homeassistant.components.rest import DOMAIN
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import DEFAULT_SCAN_INTERVAL

from tests.common import MockConfigEntry


async def setup_config_entry(
    hass: HomeAssistant,
    data: dict[str, Any],
    subentries_data: list[ConfigSubentryData] | None = None,
) -> MockConfigEntry:
    """Set up a config entry for the REST component."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
        subentries_data=subentries_data,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)

    return config_entry
