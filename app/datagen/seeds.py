"""Seed catalogs grounding the synthetic generator in realistic accounting structure.

Curated rather than downloaded so the data is fully labeled and license-clean. The structure mirrors
real sources documented in docs/design-decisions.md: MCC categories (greggles/mcc-codes), a
QuickBooks/Xero-style chart of accounts, and small-business expense category mixes.
"""
from __future__ import annotations

# QuickBooks/Xero-style chart of accounts. 1xxx assets, 2xxx liab, 3xxx equity, 4xxx revenue, 5xxx-6xxx expenses.
CHART_OF_ACCOUNTS = [
    ("1000", "Cash & Bank", "asset", "Operating bank accounts"),
    ("1200", "Accounts Receivable", "asset", "Amounts owed by clients"),
    ("1500", "Equipment", "asset", "Computers and equipment"),
    ("2000", "Accounts Payable", "liability", "Amounts owed to vendors"),
    ("3000", "Owner Equity", "equity", "Owner capital"),
    ("4000", "Service Revenue", "revenue", "Client billings"),
    ("5000", "COGS - Client Reimbursable", "expense", "Purchases billed back to a client engagement"),
    ("6010", "Travel", "expense", "Airfare, rideshare, hotels, fuel for client travel"),
    ("6020", "Meals & Entertainment", "expense", "Client and team meals, coffee, food delivery"),
    ("6100", "Advertising & Marketing", "expense", "Paid ads and marketing"),
    ("6300", "Software Subscriptions", "expense", "SaaS tools and cloud infrastructure"),
    ("6400", "Office Supplies", "expense", "Supplies and bulk office purchases"),
    ("6420", "Postage & Shipping", "expense", "Courier and shipping"),
    ("6500", "Professional Fees", "expense", "Legal, accounting, advisory"),
    ("6550", "Contract Labor", "expense", "Freelancers and contractors (1099)"),
    ("6600", "Utilities & Telecom", "expense", "Internet, phone, utilities"),
    ("6700", "Rent & Occupancy", "expense", "Office rent and coworking"),
    ("6800", "Bank & Merchant Fees", "expense", "Processor and bank fees"),
    ("6900", "Uncategorized / Ask Client", "expense", "Needs human or client clarification"),
]

EXPENSE_CODES = [c for c, _, t, _ in CHART_OF_ACCOUNTS if t == "expense" and c != "6900"]

# Vendor catalog: (canonical, default_gl, category, mcc, [aliases], (min_amt, max_amt)).
# default_gl is the "generic" coding a naive model expects; firms may override it (idiosyncratic),
# which is what the flywheel learns. Aliases drive entity resolution.
VENDOR_CATALOG = [
    ("Amazon Web Services", "6300", "cloud", "7372", ["AWS", "AMAZON WEB SERVICES", "AWS EMEA"], (60, 1400)),
    ("Notion Labs", "6300", "saas", "5734", ["Notion", "NOTION LABS INC"], (8, 200)),
    ("Figma", "6300", "saas", "5734", ["FIGMA INC", "Figma.com"], (12, 240)),
    ("Slack", "6300", "saas", "5734", ["SLACK T12345", "Slack Technologies"], (12, 300)),
    ("GitHub", "6300", "saas", "5734", ["GITHUB INC", "GitHub.com"], (21, 420)),
    ("Adobe", "6300", "saas", "5734", ["ADOBE *CREATIVE", "Adobe Inc"], (35, 600)),
    ("Zoom", "6300", "saas", "5734", ["ZOOM.US", "Zoom Video"], (15, 280)),
    ("DocuSign", "6300", "saas", "5734", ["DOCUSIGN INC"], (25, 480)),
    ("Google Ads", "6100", "ads", "7311", ["GOOGLE *ADS", "GOOGLE ADS"], (100, 3000)),
    ("Meta Platforms", "6100", "ads", "7311", ["FACEBOOK ADS", "META PLATFORMS", "FB *ADS"], (90, 2200)),
    ("LinkedIn Ads", "6100", "ads", "7311", ["LINKEDIN", "LNKD *ADS"], (80, 1600)),
    ("Uber", "6010", "rideshare", "4121", ["UBER *TRIP", "UBER TECHNOLOGIES"], (8, 90)),
    ("Lyft", "6010", "rideshare", "4121", ["LYFT *RIDE", "LYFT INC"], (8, 90)),
    ("Delta Air Lines", "6010", "airline", "3058", ["DELTA AIR", "DELTA AIRLINES"], (180, 1600)),
    ("United Airlines", "6010", "airline", "3000", ["UNITED AIR", "UA *FLIGHT"], (180, 1600)),
    ("Marriott", "6010", "hotel", "3509", ["MARRIOTT HOTELS", "COURTYARD MARRIOTT"], (140, 1100)),
    ("Chevron", "6010", "fuel", "5541", ["CHEVRON 0095", "CHEVRON GAS"], (35, 120)),
    ("Shell", "6010", "fuel", "5541", ["SHELL OIL", "SHELL SERVICE"], (35, 120)),
    ("Uber Eats", "6020", "food_delivery", "5812", ["UBER *EATS", "UBEREATS"], (20, 180)),
    ("DoorDash", "6020", "food_delivery", "5812", ["DOORDASH *ORDER", "DD *DOORDASH"], (20, 180)),
    ("Starbucks", "6020", "coffee", "5814", ["STARBUCKS #1234", "SBUX"], (5, 70)),
    ("Blue Bottle Coffee", "6020", "coffee", "5814", ["BLUE BOTTLE", "BLUEBOTTLE COFFEE"], (5, 55)),
    ("Chipotle", "6020", "restaurant", "5812", ["CHIPOTLE 0420", "CHIPOTLE MEXICAN"], (12, 160)),
    ("Amazon.com", "6400", "retail", "5942", ["AMAZON", "AMZN Mktp US", "AMZN.COM/BILL", "AMAZON MKTPL"], (12, 400)),
    ("Costco Wholesale", "6400", "wholesale", "5300", ["COSTCO WHSE", "COSTCO #0123"], (90, 700)),
    ("Staples", "6400", "office", "5943", ["STAPLES 00123", "STAPLES.COM"], (18, 320)),
    ("Apex Supplies Co", "5000", "supplier", "5085", ["APEX SUPPLIES", "APEX SUPPLY CO"], (150, 1900)),
    ("FedEx", "6420", "shipping", "4215", ["FEDEX 1234", "FEDEX OFFICE"], (12, 160)),
    ("The UPS Store", "6420", "shipping", "4215", ["UPS STORE 456", "THE UPS STORE"], (10, 110)),
    ("Upwork", "6550", "contractor", "7361", ["UPWORK *FREELANCE", "UPWORK INC"], (200, 2600)),
    ("Fiverr", "6550", "contractor", "7361", ["FIVERR *ORDER", "FIVERR INTL"], (40, 600)),
    ("WeWork", "6700", "coworking", "6513", ["WEWORK", "WE WORK 0567"], (250, 1400)),
    ("Verizon", "6600", "telecom", "4814", ["VERIZON WRLS", "VZWRLSS"], (60, 360)),
    ("Comcast", "6600", "telecom", "4899", ["COMCAST CABLE", "XFINITY"], (60, 360)),
    ("AT&T", "6600", "telecom", "4814", ["ATT*BILL", "AT&T MOBILITY"], (55, 340)),
    ("LegalZoom", "6500", "legal", "8111", ["LEGALZOOM.COM", "LEGAL ZOOM"], (100, 800)),
    ("Gusto", "6500", "payroll_svc", "8931", ["GUSTO *PAYROLL", "GUSTO INC"], (40, 500)),
    ("Stripe", "6800", "processor", "6012", ["STRIPE FEE", "STRIPE *FEES"], (5, 250)),
    ("QuickBooks", "6300", "saas", "5734", ["INTUIT *QBOOKS", "QUICKBOOKS ONLINE"], (25, 200)),
]

CLIENT_INDUSTRIES = [
    "SaaS Startup", "Marketing Agency", "Law Firm", "Dental Practice", "Restaurant Group",
    "E-commerce Retailer", "Construction LLC", "Real Estate Brokerage", "Consulting Firm",
    "Fitness Studio", "Nonprofit", "Medical Clinic", "Design Studio", "Logistics Company",
]

ROLES = ["partner", "manager", "associate", "admin"]

# Monthly seasonality index (tax-season weighting; Q1/Q4 heavier).
SEASONAL_INDEX = {1: 1.35, 2: 1.4, 3: 1.45, 4: 1.3, 5: 0.95, 6: 0.9,
                  7: 0.9, 8: 0.95, 9: 1.05, 10: 1.1, 11: 1.2, 12: 1.3}

# Scale tiers: firms, clients/firm, months, txns/client/month, docs/client.
SCALE_TIERS = {
    "test": dict(firms=2, clients=3, months=2, txns=20, docs=6),
    "cloud": dict(firms=4, clients=8, months=3, txns=35, docs=12),   # light: fast Aura seed, free-tier RAM
    "demo": dict(firms=10, clients=15, months=4, txns=60, docs=16),
    "showcase": dict(firms=20, clients=25, months=6, txns=90, docs=40),
    "big": dict(firms=40, clients=40, months=6, txns=110, docs=60),
}
