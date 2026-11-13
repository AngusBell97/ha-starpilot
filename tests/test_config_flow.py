"""Setting up a comma from the Home Assistant UI."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.starpilot.api import GalaxyAccessError, GalaxyConnectionError
from custom_components.starpilot.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import FakeGalaxy


async def test_setup(hass: HomeAssistant, galaxy: FakeGalaxy) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: " 192.168.1.50 ", CONF_PORT: 8082}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "comma four"
    assert result["data"] == {CONF_HOST: "192.168.1.50", CONF_PORT: 8082}
    assert result["result"].unique_id == "thegalaxy-ab12"


async def test_errors_then_success(hass: HomeAssistant, galaxy: FakeGalaxy) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    for error, key in (
        (GalaxyConnectionError("timed out"), "cannot_connect"),
        (GalaxyAccessError("Local access only"), "not_local"),
        (RuntimeError("boom"), "unknown"),
    ):
        galaxy.error = error
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.1.50", CONF_PORT: 8082}
        )
        assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": key}

    galaxy.error = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.50", CONF_PORT: 8082}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_same_comma_twice_updates_the_address(hass: HomeAssistant, entry: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.77", CONF_PORT: 8082}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "192.168.1.77"


async def test_without_hotspot_name(hass: HomeAssistant, galaxy: FakeGalaxy) -> None:
    del galaxy.replies["/api/galaxy/hotspot"]
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.50", CONF_PORT: 8082}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY and result["result"].unique_id is None


async def test_reconfigure(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    result = await loaded.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99", CONF_PORT: 8082}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    assert loaded.data[CONF_HOST] == "192.168.1.99"


async def test_reconfigure_wrong_device(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    galaxy.replies["/api/galaxy/hotspot"]["config"]["ssid"] = "TheGalaxy-ffff"
    result = await loaded.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99", CONF_PORT: 8082}
    )
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "wrong_device"
    assert loaded.data[CONF_HOST] == "192.168.1.50"
