#!/usr/bin/env python3
"""
Main test suite for the Hipocrate API
"""
import asyncio
import aiohttp
import os

# Import test functions from separate modules
from tests.root import test_root_endpoint
from tests.auth import test_login_endpoint_success, test_login_endpoint_missing_credentials, test_login_endpoint_invalid_json
from tests.patients import test_patient_search_endpoint, test_invalid_patient_search, test_patient_endpoint_missing_id
from tests.analyses import test_analyses_endpoint_missing_id
from tests.reports import test_report_endpoint_missing_id
from tests.checkout import test_checkout_endpoint_missing_id
from tests.cnp import test_cnp_validation_endpoint, test_cnp_validation_missing_id
from tests.extractors import test_extract_text_after_label_basic, test_extract_text_after_label_with_element_tag, test_extract_text_after_label_with_stop_at, test_extract_text_after_label_not_found, test_extract_text_after_label_case_insensitive

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

async def run_all_tests() -> None:
    """Run all API tests"""
    print(f"Starting API tests against {BASE_URL}")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        tests = [
            test_root_endpoint,
            test_login_endpoint_success,
            test_login_endpoint_missing_credentials,
            test_login_endpoint_invalid_json,
            test_patient_search_endpoint,
            test_invalid_patient_search,
            test_patient_endpoint_missing_id,
            test_analyses_endpoint_missing_id,
            test_report_endpoint_missing_id,
            test_checkout_endpoint_missing_id,
            test_cnp_validation_endpoint,
            test_cnp_validation_missing_id,
            test_extract_text_after_label_basic,
            test_extract_text_after_label_with_element_tag,
            test_extract_text_after_label_with_stop_at,
            test_extract_text_after_label_not_found,
            test_extract_text_after_label_case_insensitive
        ]
        
        results = []
        for test in tests:
            try:
                result = await test(session)
                results.append(result)
            except Exception as e:
                print(f"Test {test.__name__} failed with exception: {e}")
                results.append(False)
            print()
        
        # Summary
        passed = sum(results)
        total = len(results)
        print("=" * 50)
        print(f"Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("All tests passed! 🎉")
        else:
            print(f"{total - passed} tests failed. ❌")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
