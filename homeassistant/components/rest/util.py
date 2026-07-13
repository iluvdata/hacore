"""Helpers for RESTful API."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.typing import ConfigType

from .binary_sensor import RestBinarySensor
from .data import RestData
from .entity import RestEntity
from .sensor import RestSensor


@callback
def async_validate_rest_entity(
    hass: HomeAssistant, rest: RestData, config: ConfigType, platform: Platform
) -> RestEntity:
    """Validates a RESTful entity."""

    entity: RestEntity | None = None
    if platform == Platform.BINARY_SENSOR:
        entity = RestBinarySensor(hass, None, rest, config)
    elif platform == Platform.SENSOR:
        entity = RestSensor(hass, None, rest, config)
    if entity is None:
        raise HomeAssistantError("invalid platform")
    entity.update_from_rest_data()

    return entity
