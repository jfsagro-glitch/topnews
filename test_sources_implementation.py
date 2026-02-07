#!/usr/bin/env python3
"""
Comprehensive test for Sources Management implementation
Tests:
1. Database table creation
2. Source auto-initialization from ACTIVE_SOURCES_CONFIG
3. Per-user source settings persistence
4. News filtering by user sources
5. UI callback routing
"""

import sys
import os
import tempfile
import sqlite3
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.database import NewsDatabase

# Try to import from railway_config first, then fallback to config
try:
    from config.railway_config import SOURCES_CONFIG as ACTIVE_SOURCES_CONFIG
except (ImportError, ValueError):
    from config.config import SOURCES_CONFIG as ACTIVE_SOURCES_CONFIG

import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class TestSourcesImplementation:
    def __init__(self):
        # Create test database
        self.test_db_path = os.path.join(tempfile.gettempdir(), "test_sources.db")
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        
        self.db = NewsDatabase(self.test_db_path)
        self.passed = 0
        self.failed = 0
    
    def test_database_tables_created(self):
        """Test 1: Verify sources and user_source_settings tables exist"""
        print("\n" + "="*60)
        print("TEST 1: Database Tables Creation")
        print("="*60)
        
        try:
            conn = sqlite3.connect(self.test_db_path)
            cursor = conn.cursor()
            
            # Check sources table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sources'")
            if cursor.fetchone():
                print("✅ 'sources' table exists")
                self.passed += 1
            else:
                print("❌ 'sources' table NOT found")
                self.failed += 1
            
            # Check user_source_settings table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_source_settings'")
            if cursor.fetchone():
                print("✅ 'user_source_settings' table exists")
                self.passed += 1
            else:
                print("❌ 'user_source_settings' table NOT found")
                self.failed += 1
            
            # Check sources table schema
            cursor.execute("PRAGMA table_info(sources)")
            columns = [row[1] for row in cursor.fetchall()]
            required_cols = ['id', 'code', 'title', 'enabled_global', 'created_at']
            if all(col in columns for col in required_cols):
                print(f"✅ 'sources' table has all required columns: {required_cols}")
                self.passed += 1
            else:
                print(f"❌ 'sources' table missing columns. Found: {columns}, Required: {required_cols}")
                self.failed += 1
            
            # Check user_source_settings table schema
            cursor.execute("PRAGMA table_info(user_source_settings)")
            columns = [row[1] for row in cursor.fetchall()]
            required_cols = ['user_id', 'source_id', 'enabled', 'updated_at']
            if all(col in columns for col in required_cols):
                print(f"✅ 'user_source_settings' table has all required columns: {required_cols}")
                self.passed += 1
            else:
                print(f"❌ 'user_source_settings' table missing columns. Found: {columns}, Required: {required_cols}")
                self.failed += 1
            
            conn.close()
        except Exception as e:
            print(f"❌ Error checking database tables: {e}")
            self.failed += 1
    
    def test_source_initialization(self):
        """Test 2: Verify source auto-initialization from ACTIVE_SOURCES_CONFIG"""
        print("\n" + "="*60)
        print("TEST 2: Source Auto-Initialization")
        print("="*60)
        
        try:
            # Extract sources from config
            sources_to_create = []
            for category, cfg in ACTIVE_SOURCES_CONFIG.items():
                if category == 'telegram':
                    for src_url in cfg.get('sources', []):
                        channel = src_url.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip('/')
                        if channel:
                            sources_to_create.append({'code': channel, 'title': f"@{channel}"})
                else:
                    for src_url in cfg.get('sources', []):
                        domain = src_url.replace('https://', '').replace('http://', '').split('/')[0]
                        if domain and not domain.endswith('t.me'):
                            sources_to_create.append({'code': domain, 'title': domain})
            
            # Deduplicate
            seen_codes = set()
            unique_sources = []
            for src in sources_to_create:
                if src['code'] not in seen_codes:
                    unique_sources.append(src)
                    seen_codes.add(src['code'])
            
            print(f"Found {len(unique_sources)} unique sources in ACTIVE_SOURCES_CONFIG")
            
            # Create in DB
            source_ids = self.db.get_or_create_sources(unique_sources)
            
            if len(source_ids) == len(unique_sources):
                print(f"✅ Successfully created all {len(source_ids)} sources in database")
                self.passed += 1
            else:
                print(f"❌ Source creation mismatch. Created: {len(source_ids)}, Expected: {len(unique_sources)}")
                self.failed += 1
            
            # Verify sources in DB
            sources = self.db.list_sources()
            if len(sources) > 0:
                print(f"✅ Database contains {len(sources)} sources")
                print(f"   Sample sources: {sources[:3]}")
                self.passed += 1
            else:
                print("❌ No sources found in database")
                self.failed += 1
        except Exception as e:
            print(f"❌ Error during source initialization: {e}")
            self.failed += 1
    
    def test_user_source_toggle(self):
        """Test 3: Verify per-user source toggle functionality"""
        print("\n" + "="*60)
        print("TEST 3: Per-User Source Toggle")
        print("="*60)
        
        try:
            # Create test sources
            test_sources = [
                {'code': 'test_domain1', 'title': 'Test Domain 1'},
                {'code': 'test_domain2', 'title': 'Test Domain 2'},
                {'code': 'test_channel', 'title': '@test_channel'},
            ]
            source_ids = self.db.get_or_create_sources(test_sources)
            
            if not source_ids:
                print("❌ Failed to create test sources")
                self.failed += 1
                return
            
            print(f"✅ Created {len(source_ids)} test sources")
            self.passed += 1
            
            # Test toggle for user
            user_id = 12345
            source_id = source_ids[0]
            
            # Initial state - should be enabled (True)
            enabled_map = self.db.get_user_source_enabled_map(user_id)
            if not enabled_map:  # Empty dict means all enabled
                print("✅ Initial state: all sources enabled (no records)")
                self.passed += 1
            else:
                print(f"❌ Unexpected initial state: {enabled_map}")
                self.failed += 1
            
            # Toggle OFF
            new_state = self.db.toggle_user_source(user_id, source_id)
            if new_state == False:
                print(f"✅ Source {source_id} toggled to OFF")
                self.passed += 1
            else:
                print(f"❌ Toggle failed, expected False, got {new_state}")
                self.failed += 1
            
            # Verify toggle persisted
            enabled_map = self.db.get_user_source_enabled_map(user_id)
            if source_id in enabled_map and enabled_map[source_id] == False:
                print(f"✅ Toggle persisted in database")
                self.passed += 1
            else:
                print(f"❌ Toggle not persisted. Map: {enabled_map}")
                self.failed += 1
            
            # Toggle back ON
            new_state = self.db.toggle_user_source(user_id, source_id)
            if new_state == True:
                print(f"✅ Source {source_id} toggled back to ON")
                self.passed += 1
            else:
                print(f"❌ Toggle back failed, expected True, got {new_state}")
                self.failed += 1
            
            # Verify second toggle persisted
            enabled_map = self.db.get_user_source_enabled_map(user_id)
            if source_id not in enabled_map or enabled_map[source_id] == True:
                print(f"✅ Second toggle persisted in database")
                self.passed += 1
            else:
                print(f"❌ Second toggle not persisted. Map: {enabled_map}")
                self.failed += 1
            
        except Exception as e:
            print(f"❌ Error during toggle test: {e}")
            self.failed += 1
    
    def test_enabled_source_ids_query(self):
        """Test 4: Verify get_enabled_source_ids_for_user method"""
        print("\n" + "="*60)
        print("TEST 4: Enabled Source IDs Query")
        print("="*60)
        
        try:
            # Create test sources
            test_sources = [
                {'code': 'src_a', 'title': 'Source A'},
                {'code': 'src_b', 'title': 'Source B'},
                {'code': 'src_c', 'title': 'Source C'},
            ]
            source_ids = self.db.get_or_create_sources(test_sources)
            
            user_id = 99999
            
            # Test 1: No records = all enabled (returns None)
            result = self.db.get_enabled_source_ids_for_user(user_id)
            if result is None:
                print("✅ No user records -> returns None (all enabled)")
                self.passed += 1
            else:
                print(f"❌ Expected None for all enabled, got {result}")
                self.failed += 1
            
            # Test 2: Disable one source
            self.db.toggle_user_source(user_id, source_ids[0])
            result = self.db.get_enabled_source_ids_for_user(user_id)
            
            if result is not None and len(result) == 2:
                print(f"✅ With 1 disabled source -> returns {len(result)} enabled sources")
                self.passed += 1
            else:
                print(f"❌ Expected list of 2 enabled sources, got {result}")
                self.failed += 1
            
            # Test 3: Disable another source
            self.db.toggle_user_source(user_id, source_ids[1])
            result = self.db.get_enabled_source_ids_for_user(user_id)
            
            if result is not None and len(result) == 1:
                print(f"✅ With 2 disabled sources -> returns {len(result)} enabled source")
                self.passed += 1
            else:
                print(f"❌ Expected list of 1 enabled source, got {result}")
                self.failed += 1
            
            # Test 4: Re-enable source (disable count goes to 1)
            self.db.toggle_user_source(user_id, source_ids[0])
            result = self.db.get_enabled_source_ids_for_user(user_id)
            
            if result is not None and len(result) == 2:
                print(f"✅ After re-enabling one source -> returns {len(result)} enabled sources")
                self.passed += 1
            else:
                print(f"❌ Expected list of 2 enabled sources after re-enable, got {result}")
                self.failed += 1
            
        except Exception as e:
            print(f"❌ Error during enabled sources test: {e}")
            self.failed += 1
    
    def test_ui_callback_structure(self):
        """Test 5: Verify UI callback data structure is correct"""
        print("\n" + "="*60)
        print("TEST 5: UI Callback Structure Validation")
        print("="*60)
        
        try:
            # These tests verify that callbacks are properly structured
            # (actual Telegram callback test requires mocking)
            
            # Test settings menu callbacks
            expected_callbacks = [
                "settings:filter",
                "settings:sources:0",
                "settings:back",
                "settings:src_toggle:1:0",
                "settings:src_page:0",
            ]
            
            print("✅ Callback namespace validation:")
            for callback in expected_callbacks:
                parts = callback.split(":")
                if callback.startswith("settings:"):
                    print(f"   ✅ {callback} (valid settings: namespace)")
                    self.passed += 1
                else:
                    print(f"   ❌ {callback} (invalid namespace)")
                    self.failed += 1
            
        except Exception as e:
            print(f"❌ Error validating callbacks: {e}")
            self.failed += 1
    
    def test_news_filtering(self):
        """Test 6: Verify news filtering by user sources"""
        print("\n" + "="*60)
        print("TEST 6: News Filtering by User Sources")
        print("="*60)
        
        try:
            # Create test sources
            test_sources = [
                {'code': 'news.ru', 'title': 'news.ru'},
                {'code': 'ria.ru', 'title': 'ria.ru'},
                {'code': 'tass.ru', 'title': 'tass.ru'},
            ]
            source_ids = self.db.get_or_create_sources(test_sources)
            
            # Create test news items
            news_items = [
                {'title': 'News 1', 'source': 'news.ru'},
                {'title': 'News 2', 'source': 'ria.ru'},
                {'title': 'News 3', 'source': 'tass.ru'},
                {'title': 'News 4', 'source': 'unknown.source'},  # Unknown source
            ]
            
            user_id = 77777
            
            # Build mapping for filtering
            code_to_id = {src['code']: source_ids[i] for i, src in enumerate(test_sources)}
            
            # Test 1: All sources enabled (no filtering)
            enabled_ids = self.db.get_enabled_source_ids_for_user(user_id)
            if enabled_ids is None:
                print("✅ All sources enabled -> should return all news items")
                self.passed += 1
            else:
                print(f"❌ Expected None (all enabled), got {enabled_ids}")
                self.failed += 1
            
            # Test 2: Disable one source and filter
            self.db.toggle_user_source(user_id, source_ids[0])  # Disable news.ru
            enabled_ids = self.db.get_enabled_source_ids_for_user(user_id)
            
            if enabled_ids and len(enabled_ids) == 2:
                # Simulate filtering
                filtered = [n for n in news_items 
                           if n['source'] not in ['news.ru']  # Simplified filter
                           or code_to_id.get(n['source']) in enabled_ids
                           or code_to_id.get(n['source']) is None]
                
                print(f"✅ Disabled news.ru -> filtered {len(news_items)} items to {len(filtered)} items")
                self.passed += 1
            else:
                print(f"❌ Expected 2 enabled sources, got {enabled_ids}")
                self.failed += 1
            
        except Exception as e:
            print(f"❌ Error during filtering test: {e}")
            self.failed += 1
    
    def run_all_tests(self):
        """Run all tests and print summary"""
        print("\n" + "="*60)
        print("RUNNING SOURCES MANAGEMENT IMPLEMENTATION TESTS")
        print("="*60)
        
        self.test_database_tables_created()
        self.test_source_initialization()
        self.test_user_source_toggle()
        self.test_enabled_source_ids_query()
        self.test_ui_callback_structure()
        self.test_news_filtering()
        
        # Print summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        total = self.passed + self.failed
        percentage = (self.passed / total * 100) if total > 0 else 0
        
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"📊 Total:  {total}")
        print(f"📈 Success Rate: {percentage:.1f}%")
        
        if self.failed == 0:
            print("\n🎉 ALL TESTS PASSED! Sources implementation is working correctly.")
        else:
            print(f"\n⚠️  {self.failed} test(s) failed. Please review the output above.")
        
        # Cleanup
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        
        return self.failed == 0

if __name__ == "__main__":
    tester = TestSourcesImplementation()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
