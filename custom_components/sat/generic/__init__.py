from __future__ import annotations

import logging
from typing import Mapping, Any, Optional

from homeassistant.components import input_boolean, number, switch
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event

from ..const import (
    CONF_GENERIC_BOILER_TEMPERATURE_ENTITY_ID,
    CONF_GENERIC_CONTROL_SETPOINT_ENTITY_ID,
    CONF_GENERIC_DEVICE_ACTIVE_ENTITY_ID,
    CONF_DEVICE,
    CONF_NAME,
)
from ..coordinator import DeviceState, SatDataUpdateCoordinator
from ..helpers import float_value

_LOGGER: logging.Logger = logging.getLogger(__name__)

_CONTROL_DOMAINS = {switch.DOMAIN, input_boolean.DOMAIN}


class SatGenericCoordinator(SatDataUpdateCoordinator):
    """Coordinator that reads and controls user-selected entities."""

    def __init__(self, hass: HomeAssistant, config_data: Mapping[str, Any], options: Mapping[str, Any] | None = None) -> None:
        super().__init__(hass, config_data, options)

        self._control_setpoint_entity_id = config_data.get(CONF_GENERIC_CONTROL_SETPOINT_ENTITY_ID)
        self._boiler_temperature_entity_id = config_data.get(CONF_GENERIC_BOILER_TEMPERATURE_ENTITY_ID)
        self._device_active_entity_id = config_data.get(CONF_GENERIC_DEVICE_ACTIVE_ENTITY_ID)
        self._assumed_device_active = False

    @property
    def device_id(self) -> str:
        return str(self._config_data.get(CONF_DEVICE) or self._config_data.get(CONF_NAME))

    @property
    def device_type(self) -> str:
        return "Generic Entities"

    @property
    def supports_setpoint_management(self):
        return True

    @property
    def supports_hot_water_setpoint_management(self):
        return False

    @property
    def supports_relative_modulation(self):
        return False

    @property
    def supports_relative_modulation_management(self):
        return False

    @property
    def supports_maximum_setpoint_management(self):
        return False

    @property
    def device_active(self) -> bool:
        if not self._device_active_entity_id:
            return self._assumed_device_active

        state = self.hass.states.get(self._device_active_entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return self._assumed_device_active

        return state.state == STATE_ON

    @property
    def setpoint(self) -> Optional[float]:
        return self._get_float_state(self._control_setpoint_entity_id)

    @property
    def boiler_temperature(self) -> Optional[float]:
        return self._get_float_state(self._boiler_temperature_entity_id)

    @property
    def member_id(self) -> Optional[int]:
        return None

    async def async_added_to_hass(self) -> None:
        entities = [
            self._control_setpoint_entity_id,
            self._boiler_temperature_entity_id,
            self._device_active_entity_id,
        ]
        entities = [entity_id for entity_id in entities if entity_id]
        if entities:
            async_track_state_change_event(self.hass, entities, self.async_state_change_event)

        await super().async_added_to_hass()

    async def async_state_change_event(self, _event: Event[EventStateChangedData]):
        await self.async_notify_listeners()

    async def async_set_control_setpoint(self, value: float) -> None:
        if not self._simulation and self._control_setpoint_entity_id:
            payload = {ATTR_ENTITY_ID: self._control_setpoint_entity_id, "value": value}
            await self.hass.services.async_call(number.DOMAIN, number.SERVICE_SET_VALUE, payload, blocking=True)

        await super().async_set_control_setpoint(value)

    async def async_set_heater_state(self, state: DeviceState) -> None:
        self._assumed_device_active = state == DeviceState.ON

        if not self._simulation and self._device_active_entity_id:
            domain = self._device_active_entity_id.split(".", 1)[0]
            if domain in _CONTROL_DOMAINS:
                service = SERVICE_TURN_ON if state == DeviceState.ON else SERVICE_TURN_OFF
                payload = {ATTR_ENTITY_ID: self._device_active_entity_id}
                await self.hass.services.async_call(domain, service, payload, blocking=True)

        await super().async_set_heater_state(state)

    def _get_float_state(self, entity_id: Optional[str]) -> Optional[float]:
        if not entity_id:
            return None

        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None

        return float_value(state.state)
