#!/usr/bin/env python3
"""Test script to simulate MCP tool calls and find the NoneType error."""

import asyncio
import json
import sys
from collections import defaultdict

sys.path.append('.')

from azure_pricing_server import pricing_server, AzurePricingServer

async def test_mcp_tool_call():
    """Test the exact MCP tool call that's causing the error."""
    
    # Test the exact call that was failing
    arguments = {
        "service_name": "Virtual Machines",
        "sku_name": "Standard_F16", 
        "price_type": "Consumption",
        "limit": 10
    }
    
    print("Testing MCP tool call with arguments:")
    print(json.dumps(arguments, indent=2))
    print()
    
    try:
        async with pricing_server:
            result = await pricing_server.search_azure_prices(**arguments)
            print("Raw result:")
            print(json.dumps(result, indent=2))
            print()
            
            # Now test the formatting part that happens in the tool handler
            if result["items"]:
                formatted_items = []
                for item in result["items"]:
                    formatted_items.append({
                        "service": item.get("serviceName"),
                        "product": item.get("productName"),
                        "sku": item.get("skuName"),
                        "region": item.get("armRegionName"),
                        "location": item.get("location"),
                        "price": item.get("retailPrice"),
                        "unit": item.get("unitOfMeasure"),
                        "type": item.get("type"),
                        "savings_plans": item.get("savingsPlan", [])
                    })
                print("Formatted items:")
                print(json.dumps(formatted_items, indent=2))
            else:
                print("No items to format")
                
    except Exception as e:
        print("ERROR:", str(e))
        import traceback
        traceback.print_exc()

async def test_edge_cases():
    """Test edge cases that might cause NoneType errors."""
    
    print("\n=== Testing Edge Cases ===\n")
    
    edge_cases = [
        {"service_name": None, "sku_name": "Standard_F16"},
        {"service_name": "Virtual Machines", "sku_name": None},
        {"service_name": "", "sku_name": "Standard_F16"},
        {"service_name": "Virtual Machines", "sku_name": ""},
        {},  # Empty arguments
    ]
    
    for i, args in enumerate(edge_cases, 1):
        print(f"Edge case {i}: {args}")
        try:
            async with pricing_server:
                result = await pricing_server.search_azure_prices(**args)
                print(f"  Success: {result['count']} items found")
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
        print()


async def explore_vm_skus():
    """Discover VM SKUs then probe a handful for detailed results."""
    print("\n=== Exploring VM SKUs (top 50) ===\n")

    async with pricing_server:
        base_result = await pricing_server.search_azure_prices(
            service_name="Virtual Machines",
            limit=50,
        )

    items = base_result.get("items", [])
    sku_prices = defaultdict(list)

    for item in items:
        sku = item.get("skuName")
        if not sku:
            continue
        sku_prices[sku].append(
            {
                "region": item.get("armRegionName"),
                "price": item.get("retailPrice"),
                "unit": item.get("unitOfMeasure"),
                "meter": item.get("meterName"),
            }
        )

    unique_skus = list(sku_prices.keys())
    print(f"Fetched {len(items)} items, {len(unique_skus)} unique SKUs")
    print("Sample SKUs:")
    for sku in unique_skus[:10]:
        sample = sku_prices[sku][0]
        print(f"  - {sku}: {sample['price']} {sample['unit']} ({sample['region']})")

    # Probe a few SKUs with a more specific query to ensure they return data
    probe_skus = unique_skus[:5]
    print("\nProbing first 5 SKUs individually (limit 3 results each)...")
    for sku in probe_skus:
        try:
            async with pricing_server:
                detail = await pricing_server.search_azure_prices(
                    service_name="Virtual Machines",
                    sku_name=sku,
                    limit=3,
                )
            print(f"- {sku}: {detail['count']} results")
            if detail.get("items"):
                top = detail["items"][0]
                print(
                    json.dumps(
                        {
                            "product": top.get("productName"),
                            "region": top.get("armRegionName"),
                            "price": top.get("retailPrice"),
                            "unit": top.get("unitOfMeasure"),
                        },
                        indent=2,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            print(f"  error probing {sku}: {exc}")


async def test_currency_handling():
    """Verify prices can be retrieved in multiple currencies for a known SKU."""
    print("\n=== Currency check (USD vs EUR) ===\n")

    sku = "D4as v7"
    region = "brazilsouth"
    service = "Virtual Machines"

    async def fetch(currency: str):
        async with pricing_server:
            return await pricing_server.search_azure_prices(
                service_name=service,
                sku_name=sku,
                region=region,
                currency_code=currency,
                limit=1,
            )

    usd = await fetch("USD")
    eur = await fetch("EUR")

    def extract(result: dict) -> dict:
        item = (result.get("items") or [None])[0] or {}
        return {
            "count": result.get("count"),
            "price": item.get("retailPrice"),
            "currency": result.get("currency"),
            "product": item.get("productName"),
            "unit": item.get("unitOfMeasure"),
            "region": item.get("armRegionName"),
        }

    usd_sample = extract(usd)
    eur_sample = extract(eur)

    print("USD sample:")
    print(json.dumps(usd_sample, indent=2))
    print("EUR sample:")
    print(json.dumps(eur_sample, indent=2))

    # Basic sanity: both returned at least one result
    if (usd_sample["count"] or 0) == 0:
        print("Warning: USD query returned no items")
    if (eur_sample["count"] or 0) == 0:
        print("Warning: EUR query returned no items")

if __name__ == "__main__":
    asyncio.run(test_mcp_tool_call())
    asyncio.run(test_edge_cases())
    asyncio.run(explore_vm_skus())
    asyncio.run(test_currency_handling())