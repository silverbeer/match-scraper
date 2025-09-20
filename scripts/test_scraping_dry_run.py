#!/usr/bin/env python3
"""
Dry run test for MLS scraper to verify configuration and setup.

This script tests the scraper setup without actually running browser automation,
useful for verifying configuration and dependencies.
"""

import os
import sys
from datetime import date, timedelta

# Add project root to path for imports
project_root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, project_root)

from src.scraper.config import ScrapingConfig, load_config, validate_config
from src.scraper.mls_scraper import MLSScraper


def test_configuration():
    """Test configuration loading and validation."""
    print("⚙️  Testing Configuration")
    print("-" * 30)
    
    # Test manual configuration
    try:
        config = ScrapingConfig(
            age_group="U14",
            club="",
            competition="",
            division="Northeast",
            look_back_days=7,
            start_date=date.today() - timedelta(days=7),
            end_date=date.today(),
            missing_table_api_url="https://api.missing-table.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )
        
        print(f"   ✅ Manual config created successfully")
        print(f"      Age Group: {config.age_group}")
        print(f"      Division: {config.division}")
        print(f"      Date Range: {config.start_date} to {config.end_date}")
        
        # Test validation
        validate_config(config)
        print(f"   ✅ Configuration validation passed")
        
        return config
        
    except Exception as e:
        print(f"   ❌ Configuration error: {e}")
        return None


def test_scraper_initialization(config):
    """Test scraper initialization without running."""
    print("\n🤖 Testing Scraper Initialization")
    print("-" * 30)
    
    try:
        scraper = MLSScraper(config)
        print(f"   ✅ MLSScraper created successfully")
        
        # Test metrics initialization
        metrics = scraper.get_execution_metrics()
        print(f"   ✅ Metrics initialized: {metrics.games_scheduled} scheduled, {metrics.games_scored} scored")
        
        # Test configuration access
        print(f"   ✅ Config accessible: {scraper.config.age_group} {scraper.config.division}")
        
        return scraper
        
    except Exception as e:
        print(f"   ❌ Scraper initialization error: {e}")
        return None


def test_dependencies():
    """Test that all required dependencies are available."""
    print("\n📦 Testing Dependencies")
    print("-" * 30)
    
    dependencies = [
        ("playwright", "Playwright for browser automation"),
        ("pydantic", "Pydantic for data validation"),
        ("opentelemetry", "OpenTelemetry for metrics"),
        ("aws_lambda_powertools", "AWS Lambda Powertools for logging"),
    ]
    
    for module_name, description in dependencies:
        try:
            __import__(module_name)
            print(f"   ✅ {module_name}: {description}")
        except ImportError as e:
            print(f"   ❌ {module_name}: Missing - {e}")


def test_environment():
    """Test environment setup."""
    print("\n🌍 Testing Environment")
    print("-" * 30)
    
    # Check required directories
    directories = [
        "src/scraper",
        "tests/integration", 
        "tests/unit",
        "scripts"
    ]
    
    for directory in directories:
        if os.path.exists(directory):
            print(f"   ✅ Directory exists: {directory}")
        else:
            print(f"   ❌ Directory missing: {directory}")
    
    # Check environment variables (optional)
    env_vars = [
        ("LOG_LEVEL", "INFO"),
        ("MISSING_TABLE_API_URL", None),
        ("MISSING_TABLE_API_KEY", None),
    ]
    
    for var_name, default in env_vars:
        value = os.getenv(var_name, default)
        if value:
            print(f"   ✅ {var_name}: {value}")
        else:
            print(f"   ⚠️  {var_name}: Not set (will use default)")


def main():
    """Main function to run dry run tests."""
    
    print("🧪 MLS Match Scraper - Dry Run Test")
    print("This tool verifies setup without running browser automation")
    print("=" * 60)
    
    # Set test environment variables
    os.environ.setdefault("LOG_LEVEL", "INFO")
    os.environ.setdefault("MISSING_TABLE_API_URL", "https://api.missing-table.com")
    os.environ.setdefault("MISSING_TABLE_API_KEY", "test-key")
    
    # Run tests
    test_dependencies()
    test_environment()
    
    config = test_configuration()
    if config:
        scraper = test_scraper_initialization(config)
        
        if scraper:
            print("\n" + "=" * 60)
            print("✅ Dry run completed successfully!")
            print("\nNext steps:")
            print("1. Run parsing tests: python scripts/test_parsing_only.py")
            print("2. Run full scraping test: python scripts/test_scraping_manual.py")
            print("3. Check that browser automation works correctly")
        else:
            print("\n❌ Scraper initialization failed")
    else:
        print("\n❌ Configuration test failed")


if __name__ == "__main__":
    main()