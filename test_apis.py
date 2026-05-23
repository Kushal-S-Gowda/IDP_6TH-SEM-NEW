#!/usr/bin/env python3
"""
Comprehensive test script for FloodSense Pro Early Warning and Fire Alert System
Tests all enhanced API endpoints to ensure real data integration is working
"""

import requests
import json
from datetime import datetime

def test_api_endpoint(name, url, expected_keys=None):
    """Test a single API endpoint"""
    print(f"\n{'='*60}")
    print(f"Testing {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"✅ Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Response Type: {type(data)}")
            
            # Check for expected keys
            if expected_keys:
                missing_keys = [key for key in expected_keys if key not in data]
                if missing_keys:
                    print(f"⚠️  Missing Keys: {missing_keys}")
                else:
                    print(f"✅ All Expected Keys Present: {expected_keys}")
            
            # Display key information
            if 'status' in data:
                print(f"📊 Data Status: {data['status']}")
            
            # Show sample of data
            print(f"📄 Sample Response:")
            print(json.dumps(data, indent=2)[:500] + "..." if len(json.dumps(data)) > 500 else json.dumps(data, indent=2))
            
            return True, data
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return False, None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request Error: {str(e)}")
        return False, None
    except json.JSONDecodeError as e:
        print(f"❌ JSON Decode Error: {str(e)}")
        return False, None

def main():
    """Run comprehensive tests"""
    print(f"\n🚀 FloodSense Pro - Comprehensive API Test")
    print(f"📅 Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    base_url = "http://127.0.0.1:5000"
    
    # Test endpoints
    endpoints = [
        {
            "name": "Early Warning Forecast (Enhanced with OpenWeatherMap)",
            "url": f"{base_url}/api/early-warning/forecast",
            "expected_keys": ["status", "zones", "system_lead_time_hours", "model", "warnings_active"]
        },
        {
            "name": "Early Warning Signals (Enhanced with Real Data)",
            "url": f"{base_url}/api/early-warning/signals", 
            "expected_keys": ["status", "wind_speed_kmh", "humidity_pct", "rainfall_24h_mm", "lake_level_pct", "drain_capacity_pct", "fire_weather_index", "flood_risk_signal", "manmade_risk_signal", "combined_alert_level"]
        },
        {
            "name": "Fire Conditions (Live Weather)",
            "url": f"{base_url}/api/fire/conditions",
            "expected_keys": ["status", "wind_speed_kmh", "wind_direction", "humidity", "temperature", "fuel_moisture", "weather_desc", "fire_danger", "danger_score"]
        },
        {
            "name": "Fire Alert System (New Implementation)",
            "url": f"{base_url}/api/fire/alerts",
            "expected_keys": ["status", "alert_level", "active_alerts", "spread_risk_score", "conditions", "recommendations"]
        }
    ]
    
    results = []
    
    for endpoint in endpoints:
        success, data = test_api_endpoint(**endpoint)
        results.append({
            "name": endpoint["name"],
            "success": success,
            "data": data
        })
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 TEST SUMMARY")
    print(f"{'='*60}")
    
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    print(f"✅ Successful Tests: {len(successful)}/{len(results)}")
    print(f"❌ Failed Tests: {len(failed)}/{len(results)}")
    
    if successful:
        print(f"\n🎉 WORKING ENDPOINTS:")
        for r in successful:
            status = r["data"].get("status", "N/A")
            print(f"   ✅ {r['name']} - Status: {status}")
    
    if failed:
        print(f"\n💥 FAILED ENDPOINTS:")
        for r in failed:
            print(f"   ❌ {r['name']}")
    
    # Data Quality Check
    print(f"\n{'='*60}")
    print("🔍 DATA QUALITY ANALYSIS")
    print(f"{'='*60}")
    
    live_endpoints = [r for r in successful if r["data"].get("status") == "live"]
    demo_endpoints = [r for r in successful if r["data"].get("status") == "demo_mode"]
    
    print(f"📡 Live Data Endpoints: {len(live_endpoints)}")
    print(f"🎭 Demo Mode Endpoints: {len(demo_endpoints)}")
    
    if live_endpoints:
        print(f"\n✅ Real-time OpenWeatherMap Integration: WORKING")
        for r in live_endpoints:
            data = r["data"]
            if "current_conditions" in data:
                print(f"   🌡️  {r['name']}: {data['current_conditions'].get('weather_desc', 'N/A')}")
            if "current_weather" in data:
                print(f"   🌡️  {r['name']}: {data['current_weather'].get('weather_desc', 'N/A')}")
            if "weather_desc" in data:
                print(f"   🌡️  {r['name']}: {data['weather_desc']}")
    
    print(f"\n🏁 TEST COMPLETED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
