"""The only writers of business state (users, items, outfits, outfit_items, feedback_events,
wardrobe_images).

Routers check auth, input shape and entitlements, then call one function here. Services never call
app.ai; infrastructure tables (ai_requests, usage_counters, …) have their own narrow writers.
"""
