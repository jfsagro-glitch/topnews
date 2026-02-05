#!/usr/bin/env python3
"""Debug script to check defaults"""

import os
from core.services.access_control import AI_CLEANUP_LEVEL_DEFAULT

print(f"Default cleanup level: {AI_CLEANUP_LEVEL_DEFAULT}")
print(f"Environment AI_CLEANUP_LEVEL_DEFAULT: {os.getenv('AI_CLEANUP_LEVEL_DEFAULT', 'not set')}")
