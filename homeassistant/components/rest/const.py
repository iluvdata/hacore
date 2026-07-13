"""The rest component constants."""

from homeassistant.const import Platform
from homeassistant.util.ssl import SSLCipherList

DOMAIN = "rest"

DEFAULT_METHOD = "GET"
DEFAULT_VERIFY_SSL = True
DEFAULT_SSL_CIPHER_LIST = SSLCipherList.PYTHON_DEFAULT
DEFAULT_FORCE_UPDATE = False
DEFAULT_ENCODING = "UTF-8"
DEFAULT_SCAN_INTERVAL = 30  # seconds
MIN_SCAN_INTERVAL = 5  # seconds
CONF_ENCODING = "encoding"
CONF_SSL_SECTION = "ssl_section"
CONF_SSL_CIPHER_LIST = "ssl_cipher_list"

DEFAULT_BINARY_SENSOR_NAME = "REST Binary Sensor"
DEFAULT_SENSOR_NAME = "REST Sensor"
CONF_JSON_ATTRS = "json_attributes"
CONF_JSON_ATTRS_PATH = "json_attributes_path"

METHODS = ["POST", "GET"]

XML_MIME_TYPES = (
    "application/rss+xml",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
)

CONF_PAYLOAD_TEMPLATE = "payload_template"

ENTRY_PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]

PLATFORMS = [
    Platform.NOTIFY,
    Platform.SENSOR,
]
