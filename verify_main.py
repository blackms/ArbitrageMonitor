"""Verification script for main.py application entry point"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import structlog

# Configure logging for verification
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()


def verify_imports():
    """Verify all required imports are available"""
    logger.info("verifying_imports")
    
    try:
        from main import Application, main
        logger.info("imports_verified", status="success")
        return True
    except ImportError as e:
        logger.error("import_failed", error=str(e))
        return False


def verify_application_structure():
    """Verify Application class structure"""
    logger.info("verifying_application_structure")
    
    try:
        from main import Application
        
        # Check required methods exist
        required_methods = [
            "initialize",
            "start",
            "stop",
            "setup_signal_handlers",
            "wait_for_shutdown",
        ]
        
        for method in required_methods:
            if not hasattr(Application, method):
                logger.error("missing_method", method=method)
                return False
        
        logger.info("application_structure_verified", status="success")
        return True
    except Exception as e:
        logger.error("structure_verification_failed", error=str(e))
        return False


def verify_initialization_sequence():
    """Verify application initialization sequence"""
    logger.info("verifying_initialization_sequence")
    
    try:
        from main import Application
        
        # Create application instance
        app = Application()
        
        # Verify initial state
        assert app.settings is None, "Settings should be None initially"
        assert app.db_manager is None, "DB manager should be None initially"
        assert app.bsc_connector is None, "BSC connector should be None initially"
        assert app.polygon_connector is None, "Polygon connector should be None initially"
        
        logger.info("initialization_sequence_verified", status="success")
        return True
    except Exception as e:
        logger.error("initialization_verification_failed", error=str(e))
        return False


def verify_shutdown_sequence():
    """Verify shutdown sequence structure"""
    logger.info("verifying_shutdown_sequence")
    
    try:
        from main import Application
        import inspect
        
        # Get stop method source
        stop_method = inspect.getsource(Application.stop)
        
        # Verify shutdown steps are present
        required_steps = [
            "retention_service",
            "stats_aggregator",
            "bsc_scanner",
            "polygon_scanner",
            "bsc_monitor",
            "polygon_monitor",
            "ws_manager",
            "cache_manager",
            "db_manager",
        ]
        
        for step in required_steps:
            if step not in stop_method:
                logger.error("missing_shutdown_step", step=step)
                return False
        
        logger.info("shutdown_sequence_verified", status="success")
        return True
    except Exception as e:
        logger.error("shutdown_verification_failed", error=str(e))
        return False


def verify_signal_handlers():
    """Verify signal handler setup"""
    logger.info("verifying_signal_handlers")
    
    try:
        from main import Application
        import inspect
        
        # Get setup_signal_handlers method source
        method_source = inspect.getsource(Application.setup_signal_handlers)
        
        # Verify SIGTERM and SIGINT are handled
        if "SIGTERM" not in method_source or "SIGINT" not in method_source:
            logger.error("missing_signal_handlers")
            return False
        
        logger.info("signal_handlers_verified", status="success")
        return True
    except Exception as e:
        logger.error("signal_handler_verification_failed", error=str(e))
        return False


def main():
    """Run all verification checks"""
    logger.info("starting_verification")
    
    checks = [
        ("Imports", verify_imports),
        ("Application Structure", verify_application_structure),
        ("Initialization Sequence", verify_initialization_sequence),
        ("Shutdown Sequence", verify_shutdown_sequence),
        ("Signal Handlers", verify_signal_handlers),
    ]
    
    results = {}
    all_passed = True
    
    for check_name, check_func in checks:
        logger.info("running_check", check=check_name)
        result = check_func()
        results[check_name] = result
        
        if not result:
            all_passed = False
            logger.error("check_failed", check=check_name)
        else:
            logger.info("check_passed", check=check_name)
    
    # Print summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    for check_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {check_name}")
    
    print("=" * 60)
    
    if all_passed:
        print("\n✓ All verification checks passed!")
        logger.info("verification_complete", status="success")
        return 0
    else:
        print("\n✗ Some verification checks failed!")
        logger.error("verification_complete", status="failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
