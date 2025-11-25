#!/usr/bin/env python3
"""
Main test suite for the Hipocrate API
"""
import asyncio
import aiohttp
import os
import argparse
import sys
import unittest

# Import test functions from separate modules
from tests.root import test_root_endpoint
from tests.auth import test_login_endpoint_success, test_login_endpoint_missing_credentials, test_login_endpoint_invalid_json
from tests.patients import test_patient_search_endpoint, test_invalid_patient_search, test_patient_endpoint_missing_id
from tests.analyses import test_analyses_endpoint_missing_id
from tests.reports import test_report_endpoint_missing_id
from tests.checkout import test_checkout_endpoint_missing_id
from tests.cnp import test_cnp_validation_endpoint, test_cnp_validation_missing_id
from tests.extractors import test_extract_text_after_label_basic, test_extract_text_after_label_with_element_tag, test_extract_text_after_label_with_stop_at, test_extract_text_after_label_not_found, test_extract_text_after_label_case_insensitive, test_extract_text_with_bold_tag, test_extract_text_with_bold_and_underline_tags, test_extract_text_with_whitespace, test_extract_id_from_link_basic, test_extract_id_from_link_with_custom_pattern, test_extract_id_from_link_no_href, test_extract_id_from_link_no_match, test_extract_ids_from_links_basic, test_extract_ids_from_links_with_custom_pattern, test_extract_ids_from_links_no_matches
from tests.hipodata import TestHipoData
from tests.markdown import TestMarkdownConversion

# Configuration
BASE_URL = "http://localhost:44660"
HYP_USER = os.getenv("HYP_USER")
HYP_PASS = os.getenv("HYP_PASS")

# Group tests by functionality
TEST_GROUPS = {
    "all": [
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
        test_extract_text_after_label_case_insensitive,
        TestHipoData,
        TestMarkdownConversion
    ],
    "root": [test_root_endpoint],
    "auth": [
        test_login_endpoint_success,
        test_login_endpoint_missing_credentials,
        test_login_endpoint_invalid_json
    ],
    "patients": [
        test_patient_search_endpoint,
        test_invalid_patient_search,
        test_patient_endpoint_missing_id
    ],
    "analyses": [test_analyses_endpoint_missing_id],
    "reports": [test_report_endpoint_missing_id],
    "checkout": [test_checkout_endpoint_missing_id],
    "cnp": [
        test_cnp_validation_endpoint,
        test_cnp_validation_missing_id
    ],
    "extractors": [
        test_extract_text_after_label_basic,
        test_extract_text_after_label_with_element_tag,
        test_extract_text_after_label_with_stop_at,
        test_extract_text_after_label_not_found,
        test_extract_text_after_label_case_insensitive,
        test_extract_text_with_bold_tag,
        test_extract_text_with_bold_and_underline_tags,
        test_extract_text_with_whitespace,
        test_extract_id_from_link_basic,
        test_extract_id_from_link_with_custom_pattern,
        test_extract_id_from_link_no_href,
        test_extract_id_from_link_no_match,
        test_extract_ids_from_links_basic,
        test_extract_ids_from_links_with_custom_pattern,
        test_extract_ids_from_links_no_matches
    ],
    "hipodata": [TestHipoData],
    "markdown": [TestMarkdownConversion]
}

async def run_tests(test_list) -> None:
    """Run specified API tests"""
    print(f"Starting API tests against {BASE_URL}")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        results = []
        for test in test_list:
            try:
                # Handle both async test functions and unittest classes
                if hasattr(test, '__call__') and hasattr(test, '__name__'):
                    # Regular async test function
                    result = await test(session)
                    results.append(result)
                else:
                    # Unittest class - run it
                    suite = unittest.TestLoader().loadTestsFromTestCase(test)
                    runner = unittest.TextTestRunner(stream=open('/dev/null', 'w'))
                    test_result = runner.run(suite)
                    success = test_result.wasSuccessful()
                    results.append(success)
                    print(f"Test {test.__name__}: {'PASS' if success else 'FAIL'}")
            except Exception as e:
                print(f"Test {getattr(test, '__name__', str(test))} failed with exception: {e}")
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

def main():
    parser = argparse.ArgumentParser(description="Run Hipocrate API tests")
    parser.add_argument(
        "test_group", 
        nargs="?", 
        default="all",
        choices=list(TEST_GROUPS.keys()),
        help="Test group to run (default: all)"
    )
    
    args = parser.parse_args()
    
    if args.test_group not in TEST_GROUPS:
        print(f"Error: Unknown test group '{args.test_group}'")
        print(f"Available groups: {', '.join(TEST_GROUPS.keys())}")
        sys.exit(1)
    
    test_list = TEST_GROUPS[args.test_group]
    print(f"Running {args.test_group} tests ({len(test_list)} tests)")
    
    asyncio.run(run_tests(test_list))

if __name__ == "__main__":
    main()
