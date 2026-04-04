# core/sector_archetypes.py
"""
Novus Sector Archetypes – Enhanced for Indian Listed Companies
Provides qualitative guardrails and mental models for fundamental analysis.
Injects Dalal Street heuristics into qualitative agents to prevent generic LLM hallucinations.
"""

from typing import Dict, Optional, List, Tuple
import re
import difflib


class SectorArchetype:
    """Represents a sector with its specific guardrails and alternative names."""
    def __init__(self, name: str, guardrails: str, aliases: Optional[List[str]] = None):
        self.name = name
        self.guardrails = guardrails.strip()
        self.aliases = [a.strip().upper() for a in (aliases or [])]


class SectorGuardrailRegistry:
    """
    Registry for sector-specific analytical guardrails.
    Supports exact (case‑insensitive) matches, aliases, and a fallback DEFAULT sector.
    Includes fuzzy matching when exact match fails.
    """

    def __init__(self, fallback: str = "DEFAULT"):
        self._sectors: Dict[str, SectorArchetype] = {}
        self._alias_map: Dict[str, str] = {}
        self._fallback_key = fallback.upper()

    def register(self, sector: SectorArchetype) -> None:
        """Register a sector archetype and its aliases."""
        key = sector.name.upper()
        self._sectors[key] = sector
        for alias in sector.aliases:
            self._alias_map[alias] = key

    def get(self, sector_name: str, fuzzy: bool = True) -> str:
        """
        Retrieve guardrails for a given sector name.
        - First tries exact match (case‑insensitive).
        - Then tries alias match.
        - If fuzzy=True, finds the closest matching sector name using difflib.
        - Falls back to DEFAULT sector if nothing matches.
        """
        key = sector_name.upper().strip()
        # Exact match
        if key in self._sectors:
            return self._sectors[key].guardrails
        # Alias match
        if key in self._alias_map:
            return self._sectors[self._alias_map[key]].guardrails
        # Fuzzy match (optional)
        if fuzzy:
            all_names = list(self._sectors.keys())
            matches = difflib.get_close_matches(key, all_names, n=1, cutoff=0.6)
            if matches:
                return self._sectors[matches[0]].guardrails
        # Fallback
        fallback = self._sectors.get(self._fallback_key)
        if fallback:
            return fallback.guardrails
        raise KeyError(f"No sector '{sector_name}' and no DEFAULT sector registered.")

    def list_sectors(self) -> List[str]:
        """Return all registered sector names."""
        return list(self._sectors.keys())


# ----------------------------------------------------------------------
# Registry initialisation with all Indian‑listed sector archetypes
# ----------------------------------------------------------------------
registry = SectorGuardrailRegistry(fallback="DEFAULT")

# ──────────────────────────────────────────────────────────────────────
# 1. Original sectors (preserved and slightly polished)
# ──────────────────────────────────────────────────────────────────────
registry.register(SectorArchetype(
    "FMCG",
    """Working Capital: Extended payables and negative cash conversion cycles are a sign of immense competitive strength.
Capital Allocation: High dividend payouts (>80%) are standard and healthy. Growth is driven by Opex (A&P), not Capex.
Valuation: Focus on volume growth vs. price-led growth. High ROIC (>15%) is expected."""
))

registry.register(SectorArchetype(
    "RETAIL_QCOMMERCE",
    """Growth Drivers: Focus on Same-Store Sales Growth (SSSG), footfalls, and revenue per square foot.
Unit Economics: For Q-Commerce/E-commerce, track average order value (AOV) and contribution margin per order.
Capital Allocation: High lease liabilities (Ind AS 116) will inflate debt; adjust for this when calculating leverage."""
))

registry.register(SectorArchetype(
    "BFSI",
    """CRITICAL: Ignore traditional metrics like EBITDA, Working Capital, or Inventory; they do not apply to banks or NBFCs.
Profitability: Focus strictly on Net Interest Margins (NIM) and Return on Assets (RoA).
Asset Quality: Rising Gross/Net NPAs, elevated Credit Costs, or high slippages are critical kill criteria.
Liabilities: A high CASA ratio is a massive competitive advantage. Growth is driven by Loan Book/AUM expansion.""",
    aliases=["BANK", "NBFC", "FINANCIAL_SERVICES"]
))

registry.register(SectorArchetype(
    "IT_SERVICES",
    """Asset-light human capital business. Ignore physical inventory and heavy CapEx.
Growth Drivers: Focus on Total Contract Value (TCV), deal pipeline, and constant currency (CC) growth.
Margins: Track employee attrition, utilization rates, and wage hikes as primary margin levers.
Capital Allocation: High buybacks and dividends are standard and expected.""",
    aliases=["IT", "SOFTWARE", "TECH_SERVICES"]
))

registry.register(SectorArchetype(
    "PHARMA_HEALTHCARE",
    """Regulatory Risk: Actively flag any mention of USFDA inspections, Form 483 observations, OAI (Official Action Indicated), or warning letters as HIGH risk.
Growth Drivers: Distinguish between the US generics pipeline (ANDA approvals) and India domestic formulations.
Capital Allocation: R&D expenditure should be tracked as a percentage of sales. High R&D is a positive growth indicator.""",
    aliases=["PHARMA", "DRUGS", "BIOTECH"]
))

registry.register(SectorArchetype(
    "CAPITAL_GOODS_INFRA",
    """Asset-heavy and B2B focused.
Revenue Visibility: Focus entirely on 'Order Book' size and the 'Book-to-Bill' ratio.
Execution Risk: Working capital cycles are traditionally stretched, but rapidly rising receivables (unbilled revenue) is a red flag.
Capital Allocation: High CapEx is required for growth. Do not penalize for lower dividend payouts.""",
    aliases=["CAPITAL_GOODS", "INFRASTRUCTURE", "ENGINEERING"]
))

registry.register(SectorArchetype(
    "REAL_ESTATE",
    """CRITICAL: Ignore traditional P&L revenue recognition, as it is skewed by project completion accounting.
Growth Drivers: Focus entirely on 'Pre-sales' (bookings), 'Collections', and new project launch pipelines.
Balance Sheet: Debt reduction and operating cash flow are the most important health metrics.
Regulatory: Note any mentions of RERA compliance or delayed project execution.""",
    aliases=["REALTY", "PROPERTY_DEVELOPMENT"]
))

registry.register(SectorArchetype(
    "CEMENT_BUILDING_MATS",
    """Highly localized, volume-driven commodity business.
Profitability: The ultimate metric is 'EBITDA per ton'. Track capacity utilization.
Costs: Highly sensitive to power, fuel (petcoke/coal), and freight costs.
Capital Allocation: Growth requires continuous capacity additions (Brownfield/Greenfield CapEx).""",
    aliases=["CEMENT", "BUILDING_MATERIALS"]
))

registry.register(SectorArchetype(
    "METALS_MINING",
    """Hyper-cyclical, price-taker business.
Margins: Driven entirely by global LME prices and spreads.
Capital Allocation: The primary metric of management quality is deleveraging (paying down debt) during upcycles. Capital misallocation during peak cycles is a kill criterion.""",
    aliases=["METALS", "MINING", "STEEL", "ALUMINIUM", "COPPER"]
))

registry.register(SectorArchetype(
    "OIL_GAS",
    """Segment properly: Upstream (E&P), Downstream (Refining/OMC), or City Gas Distribution (CGD).
Profitability: For refiners, track Gross Refining Margins (GRM). For CGD, track volume growth and APM gas allocation.
Regulatory Risk: Highly sensitive to government intervention (Windfall taxes, subsidy sharing, APM pricing).""",
    aliases=["OIL", "GAS", "REFINERY", "PETROLEUM"]
))

registry.register(SectorArchetype(
    "CHEMICALS",
    """Distinguish between Bulk/Commodity chemicals and Specialty chemicals/CSM.
Growth Drivers: Track China+1 strategy execution, new molecule additions, and R&D spend.
Margins: Assess raw material pass-through capabilities. Inability to pass on crude-linked raw material inflation is a red flag.""",
    aliases=["CHEMICAL", "SPECIALTY_CHEMICALS"]
))

registry.register(SectorArchetype(
    "POWER_UTILITIES",
    """Highly regulated, capital-intensive sector.
Profitability: Driven by Regulated Equity and assured Return on Equity (RoE) under long-term PPAs (Power Purchase Agreements).
Risk: High debt is normal, but high receivables from state Discoms is a major cash flow risk. Track capacity addition (GW) in renewables.""",
    aliases=["POWER", "UTILITY", "ELECTRICITY"]
))

registry.register(SectorArchetype(
    "TELECOM",
    """High CapEx oligopoly.
Growth Drivers: The ultimate metric is ARPU (Average Revenue Per User) and subscriber churn rate.
Ind AS 116: Spectrum liabilities are recorded as right‑of‑use assets with corresponding lease liabilities. Do not confuse high reported debt with distress – focus on cash flow post‑spectrum payments.
Capital Allocation: Do not penalise for massive debt levels; network CapEx is structural. Track free cash flow generation after spectrum amortisation and interest."""
))

registry.register(SectorArchetype(
    "AUTO_AUTO_ANCILLARY",
    """Cyclical, asset-heavy business.
Volume Metrics: Focus on monthly wholesale dispatches vs. retail sales (Vahan registrations).
Working Capital: Monitor dealer inventory levels. High dealer inventory is a major red flag for future margins.
Disruption: Note any commentary on EV transition execution and premiumization trends.""",
    aliases=["AUTO", "AUTOMOBILE", "AUTO_COMPONENTS", "ANCILLARY"]
))

registry.register(SectorArchetype(
    "MEDIA_ENTERTAINMENT",
    """Disrupted sector transitioning to digital.
Revenue: Distinguish between ad-revenue (highly cyclical, tied to FMCG ad-spend) and subscription revenue (sticky).
Capital Allocation: Monitor content acquisition costs. High content costs with low subscriber addition is a red flag.""",
    aliases=["MEDIA", "ENTERTAINMENT", "BROADCASTING", "PRINT_MEDIA"]
))

# ──────────────────────────────────────────────────────────────────────
# 2. New sectors – covering all major Indian listed industries
# ──────────────────────────────────────────────────────────────────────

registry.register(SectorArchetype(
    "AGRI_CHEMICALS_PESTICIDES",
    """Cyclical, monsoon-dependent input sector.
Growth Drivers: Track new molecule launches, export opportunity (China+1), and channel inventory levels.
Margins: Raw material (basic chemicals) price volatility is key. High working capital during peak season is normal.
Regulatory: Monitor any bans on key molecules (e.g., Phorate, Monocrotophos) as high risk.""",
    aliases=["PESTICIDES", "AGROCHEMICALS", "CROP_CARE"]
))

registry.register(SectorArchetype(
    "FERTILIZERS",
    """Government‑controlled, subsidy‑driven business.
Critical: Never ignore subsidy receivables – they are the single biggest determinant of cash flow.
Profitability: Track 'subsidy per tonne' and timely release from government. High dependence on imported raw materials (DAP, MOP).
Valuation: Compare enterprise value to subsidy receivable + capacity.""",
    aliases=["FERTILISER", "UREA", "DAP"]
))

registry.register(SectorArchetype(
    "SUGAR",
    """Cyclical, heavily regulated commodity.
Profitability: Linked to FRP (Fair & Remunerative Price) vs. sugar realizations and ethanol blending price.
Working Capital: Massive inventory holding (sugar + molasses) – high debt is structural but rising interest costs kill margins.
Green flag: Diversion of B-heavy molasses to ethanol (EBITDA margin boost).""",
    aliases=["SUGAR_MILLS"]
))

registry.register(SectorArchetype(
    "TEXTILES_APPAREL",
    """Fragmented, export‑oriented, labour‑intensive.
Macro drivers: Cotton prices, US/Europe demand (GDP correlation), and preferential trade agreements.
Working capital: High inventory of yarn/fabric is normal; monitor days of inventory.
Margins: Power & fuel cost, labour availability (e.g., migrant labour disruptions). PLI scheme beneficiaries get a tailwind.""",
    aliases=["TEXTILE", "APPAREL", "GARMENT", "YARN", "FABRIC"]
))

registry.register(SectorArchetype(
    "HOTELS_HOSPITALITY",
    """Asset‑heavy, high operating leverage.
Profitability: The ultimate metric is RevPAR (Revenue Per Available Room) = Occupancy × Average Room Rate (ARR).
Costs: Staff costs and power are the largest opex. Seasonality (wedding season, holidays) is a key swing factor.
Capital Allocation: High debt for new properties; watch out for interest coverage ratio (ICR) < 1.5.""",
    aliases=["HOTELS", "RESORTS", "HOSPITALITY"]
))

registry.register(SectorArchetype(
    "AIRLINES",
    """Extremely cyclical, negative working capital business (advance ticket sales).
Profitability: Track RASK (Revenue per ASK) vs. CASK (Cost per ASK). Fuel (ATF) is the single largest cost – hedge policy matters.
Debt: High aircraft lease liabilities (off‑balance sheet risk). Net debt/EBITDA can be misleading due to volatility.
Regulatory: DGCA slot allocations, airport charges, and grounding of fleet (e.g., Pratt & Whitney engine issues) are critical.""",
    aliases=["AVIATION", "CARRIER"]
))

registry.register(SectorArchetype(
    "SHIPPING_LOGISTICS",
    """Freight rate driven, global cyclical.
Revenue: Track TCE (Time Charter Equivalent) per day, fleet utilisation, and Baltic Dry Index for bulkers.
Capital Allocation: High vessel CapEx – sale & leaseback transactions common. Monitor scrap value of aging fleet.
Risk: Fuel (bunker) cost, port congestion, and geopolitical (Red Sea diversions).""",
    aliases=["SHIPPING", "LOGISTICS", "FREIGHT", "WAREHOUSING"]
))

registry.register(SectorArchetype(
    "DEFENCE_AEROSPACE",
    """Government monopsony, long‑cycle, high entry barrier.
Order book: The only metric that matters – track MoD contracts, export offsets, and R&D for next‑gen platforms.
Profitability: Margins are typically low (15‑20%) due to single customer, but cash flows are lumpy.
Red flag: Delays in supply chain (imported engines/components) or sanctions on key technologies.""",
    aliases=["DEFENCE", "AEROSPACE", "MILITARY"]
))

registry.register(SectorArchetype(
    "RAILWAYS_ROLLING_STOCK",
    """Capex beneficiary of Indian Railways’ modernisation.
Growth drivers: Track annual orders from RVNL, IRFC, and private operators (e.g., Vande Bharat, freight corridors).
Margins: Highly price‑sensitive tenders – cost escalation clauses are vital. Monitor working capital for large EPC orders.
Capital Allocation: Asset turn (revenue/net block) is a key efficiency measure.""",
    aliases=["RAILWAY", "LOCOMOTIVE", "COACH"]
))

registry.register(SectorArchetype(
    "CONSTRUCTION_EPC",
    """Project‑driven, high working capital, low margin.
Critical metric: Order book diversification (government vs private, domestic vs overseas). Book‑to‑bill >1.2x is healthy.
Balance sheet: High unbilled revenue (work in progress) inflates receivables – convert to billing efficiency ratio.
Red flags: Litigation with NHAI/NHPC, arbitration awards stuck in appeals, or high related‑party advances.""",
    aliases=["EPC", "CONSTRUCTION", "INFRA_DEVELOPER"]
))

registry.register(SectorArchetype(
    "CONSUMER_DURABLES",
    """Discretionary spend, distribution‑led growth.
Growth drivers: Urban vs rural volume split, product mix shift to premium (AC, refrigerators, washing machines).
Margins: In‑house manufacturing (Capex) vs. outsourced – the former gives margin control but ties up capital.
Working capital: Channel financing schemes – high receivables from dealers are a red flag (sign of pushing inventory).""",
    aliases=["APPLIANCES", "ELECTRONICS", "DURABLES"]
))

registry.register(SectorArchetype(
    "FOOTWEAR_ACCESSORIES",
    """Brand‑led retail, high marketing intensity.
Valuation: Focus on same‑store sales growth (SSSG), store expansion metrics (per square foot revenue), and digital penetration.
Margins: Raw materials (leather, EVA, PU) are volatile; ability to pass through price hikes is key.
Capital allocation: Low CapEx – high FCF conversion. High promoter pledging is a kill criterion.""",
    aliases=["FOOTWEAR", "SHOES", "ACCESSORIES"]
))

registry.register(SectorArchetype(
    "JEWELLERY",
    """Gold‑price sensitive, inventory‑heavy, trust business.
Critical metric: Hedging policy – unhedged inventory in a falling gold price destroys equity. Conversely, underhedged rally creates super profits.
Profitability: Track making charges per gram, studded jewellery share (higher margins), and old‑gold exchange schemes.
Working capital: High inventory days (60‑90) is structural – but rising pledge of inventory to banks is a red flag.""",
    aliases=["JEWELLERY", "GOLD", "DIAMOND", "ORNAMENTS"]
))

registry.register(SectorArchetype(
    "BREWERIES_ALCOHOL",
    """State‑regulated, high excise duty, duopoly or oligopoly.
Growth drivers: Premiumisation (IMFL vs regular), market share in key states (Karnataka, Maharashtra, Kerala, Telangana).
Margins: Barley/malt costs, glass bottle prices, and distribution agreements. Excise policy changes (e.g., dry days, license fees) are binary events.
Risk: High litigation on advertising bans, health warnings, and trade receivables from state corporations.""",
    aliases=["ALCOHOL", "BREWERY", "SPIRITS", "IMFL"]
))

registry.register(SectorArchetype(
    "TOBACCO",
    """Sin good, hyper‑stable cash flow, regulatory shadow.
Profitability: Volume decline (~1‑2% p.a.) offset by pricing power – track net sales per stick.
Capital allocation: Huge dividend payouts (90%+), no debt, high RoCE. Any diversification (e.g., FMCG, hotels) should be treated skeptically.
Regulatory: PIC (Plain Packaging), GST rate hikes, and illicit trade share – all critical.""",
    aliases=["CIGARETTE", "TOBACCO_PRODUCTS"]
))

registry.register(SectorArchetype(
    "PAINTS",
    """Duopoly (Asian Paints, Berger) with high branding moat.
Growth drivers: Housing cycle, repainting frequency (every 3‑4 years), decorative vs industrial split.
Margins: Titanium dioxide (TiO2) and crude derivatives are key input costs. Ability to take price hikes during inflation is a moat.
Working capital: Dealer financing – low days receivables due to advance payments. Negative working capital is a sign of strength.""",
    aliases=["PAINT", "COATINGS"]
))

registry.register(SectorArchetype(
    "TYRES",
    """Cyclical, raw‑material sensitive, replacement demand driven.
Profitability: Natural rubber, crude oil derivatives (nylon tyre cord, carbon black) are 70% of cost. Track price spreads.
Metrics: Capacity utilisation (>85% is good), radialisation share (higher margins), and export realisation.
Capital allocation: High CapEx for radial capacity – but over‑expansion during upcycle leads to debt trap.""",
    aliases=["TYRE", "RUBBER"]
))

registry.register(SectorArchetype(
    "BATTERIES_ENERGY_STORAGE",
    """Lithium cell dependency, EV inflection point.
Growth: Track Li‑ion cell prices (falling is margin positive for assemblers). Replacement battery market for inverters/automotive.
Capital allocation: Massive planned Capex for gigafactories – partners with cell chemistry (LFP, NMC) matter.
Risk: Technology obsolescence – sodium‑ion or solid‑state breakthroughs can strand assets.""",
    aliases=["BATTERY", "ENERGY_STORAGE", "ACCUMULATOR"]
))

registry.register(SectorArchetype(
    "SOLAR_RENEWABLES",
    """Auction‑driven, tariff‑sensitive, negative working capital.
Growth: Track MW of projects won (PPA with SECI, state discoms), execution timeline, and module sourcing (domestic vs Chinese).
Profitability: EPC margins are thin (<10%); O&M is annuity. Interest rates directly impact project IRR.
Balance sheet: High project debt – monitor DSCR (Debt Service Coverage Ratio) and refinancing ability.""",
    aliases=["SOLAR", "RENEWABLE_ENERGY", "GREEN_ENERGY"]
))

registry.register(SectorArchetype(
    "ELECTRONICS_MANUFACTURING_SERVICES",
    """EMS – beneficiary of China+1 and PLI schemes.
Growth drivers: Customer concentration (Apple, Xiaomi, Samsung) – winning/losing a key client is binary.
Margins: Ultra‑thin (3‑5% net) – working capital management is survival. High inventory of imported components (chips, displays) is risky.
Capital allocation: High CapEx for SMT lines, but asset turns >2x are achievable.""",
    aliases=["EMS", "ELECTRONICS_MFG", "MOBILE_MFG"]
))

registry.register(SectorArchetype(
    "DATA_CENTERS",
    """REIT‑like cash flows but with tech risk.
Metrics: Track MW of IT load commissioned, power usage effectiveness (PUE), and contracted vs spot pricing.
Profitability: EBITDA per rack/month is key. Land + power availability (renewable PPAs) is a moat.
Capital allocation: Extremely asset heavy – debt funded. Look for long‑term take‑or‑pay contracts with cloud hyperscalers.""",
    aliases=["DATACENTER", "CLOUD_INFRA"]
))

registry.register(SectorArchetype(
    "PACKAGING_PAPER_PLASTIC",
    """Industrial commodity, B2B, working capital intensive.
Profitability: Margin = spread between raw material (kraft paper, polymer resin) and selling price.
Growth drivers: E‑commerce demand for corrugated boxes, FMCG shift to mono‑material packaging.
Capital allocation: High maintenance CapEx for paper machines. Debt/EBITDA >4x is a red flag.""",
    aliases=["PACKAGING", "PAPER", "CORRUGATION", "PLASTIC_PACKAGING"]
))

registry.register(SectorArchetype(
    "INDUSTRIAL_GASES",
    """Oligopoly (Linde, Air Liquide), long‑term take‑or‑pay contracts.
Metrics: Volume growth (Nm³), merchant vs on‑site mix. On‑site contracts provide high margin stability.
Capital allocation: High CapEx for air separation units (ASUs) but contracted returns. Monitor capacity utilisation.
Risk: Power cost (electricity is 60‑70% of opex) and captive power availability.""",
    aliases=["GASES", "OXYGEN", "NITROGEN"]
))

registry.register(SectorArchetype(
    "SECURITY_FACILITY_MANAGEMENT",
    """Labour‑intensive, low margin, high attrition.
Profitability: Revenue per man‑month, employee productivity, and client retention rate.
Margins: Minimum wage hikes directly compress margins. Contract renegotiation risk (e.g., government tenders).
Balance sheet: Low CapEx, but high working capital due to wage advances and ESI/PF deposits.""",
    aliases=["SECURITY", "FACILITY_MANAGEMENT", "MANPOWER"]
))

registry.register(SectorArchetype(
    "EDUCATION_TRAINING",
    """Regulated, high RoCE, but policy risk.
Growth drivers: Enrolment growth, average tuition fee, and campus utilisation. For ed‑tech, track customer acquisition cost (CAC) and lifetime value (LTV).
Capital allocation: For schools/colleges, land is fixed asset – expansion is lumpy. Low debt is typical.
Risk: NEP 2020 implementation, fee caps, and no‑detention policy changes.""",
    aliases=["EDUCATION", "TRAINING", "COACHING", "SCHOOL", "COLLEGE"]
))

registry.register(SectorArchetype(
    "HOSPITALS_DIAGNOSTICS",
    """Asset‑heavy, high fixed cost, occupancy driven.
Profitability: ARPOB (Average Revenue Per Occupied Bed), bed occupancy rate (target >75%), and average length of stay.
Revenue mix: Surgery vs medicine, cash vs insurance (TPA). Insurance collection cycles stretch working capital.
Capital allocation: High Capex for new hospitals – payback periods of 5‑7 years. Monitor same‑store growth carefully.""",
    aliases=["HOSPITAL", "DIAGNOSTIC", "PATHOLOGY", "RADIOLOGY"]
))

registry.register(SectorArchetype(
    "MEDICAL_DEVICES_EQUIPMENT",
    """Technology + regulatory play.
Growth: Replacement demand, new product introductions (e.g., stents, MRI, ventilators). Import substitution under PLI.
Profitability: High R&D spend is positive. Distribution channel strength (tie‑ups with hospital chains).
Regulatory: NMPB price caps (e.g., stents, knee implants) can crush margins overnight.""",
    aliases=["MEDTECH", "MEDICAL_EQUIPMENT", "DEVICES"]
))

registry.register(SectorArchetype(
    "INSURANCE_LIFE",
    """Long‑duration, regulatory‑driven, embedded value (EV) accounting.
Critical metric: Value of New Business (VNB) and VNB margin. Track annualised premium equivalent (APE) growth.
Profitability: Persistency ratio (13th month, 49th month) – low persistency kills long‑term value.
Balance sheet: Solvency margin (>1.5x required). High exposure to corporate bonds is a red flag.""",
    aliases=["LIFE_INSURANCE", "LIC", "INSURER"]
))

registry.register(SectorArchetype(
    "INSURANCE_GENERAL",
    """Short‑tail underwriting, combined ratio is king.
Metrics: Combined ratio (loss ratio + expense ratio) <100% indicates underwriting profit. Track gross direct premium (GDP) growth.
Investment income: Float from premiums is invested – interest rate sensitivity is high.
Red flags: Rising claims from motor (third‑party) or health (fraud). High reinsurance dependency is a risk.""",
    aliases=["GENERAL_INSURANCE", "HEALTH_INSURANCE", "MOTOR_INSURANCE"]
))

registry.register(SectorArchetype(
    "ASSET_MANAGEMENT",
    """AUM‑driven, low CapEx, high operating leverage.
Metrics: Quarterly average AUM, equity vs debt mix (equity yields higher fees), and retail vs institutional split.
Profitability: EBITDA/AUM basis points (bps). High market share in SIP flows is sticky.
Capital allocation: Most MFs are subsidiaries – watch for repatriation of dividends. High related‑party transactions (to sponsor) is a red flag.""",
    aliases=["MUTUAL_FUND", "AMC", "WEALTH_MANAGEMENT"]
))

registry.register(SectorArchetype(
    "STOCK_EXCHANGE",
    """Monopoly/duopoly (NSE, BSE), regulatory sandbox.
Metrics: Average daily turnover (ADT) in cash, F&O, and commodity segments. Clearing corporation fees.
Profitability: Operating leverage is extreme – incremental margin >80%. Track transaction charges and annual listing fees.
Risk: Regulatory changes (e.g., T+0 settlement, shorter F&O expiry) or technology disruptions.""",
    aliases=["EXCHANGE", "DEPOSITORY", "CDSL", "NSDL"]
))

registry.register(SectorArchetype(
    "RATING_AGENCY",
    """Oligopoly (CRISIL, ICRA, CARE, India Ratings). Business model: issuer‑pays.
Metrics: Outstanding rated instruments (volume), number of upgrades/downgrades, and market share in bank loan ratings.
Profitability: High margins (40%+ EBITDA), low CapEx. Key risk is conflict of interest or regulatory censure.
Growth: Tied to corporate bond market issuance and bank credit growth.""",
    aliases=["RATING", "CREDIT_RATING"]
))

registry.register(SectorArchetype(
    "MICROFINANCE",
    """High yield, high credit cost, social objective.
Critical metric: Portfolio at Risk (PAR) >30 days, collection efficiency, and borrower over‑leverage (more than 2 MFIs).
Profitability: Net interest margin (NIM) >10% is typical, but provisions for bad loans (credit cost) erode it.
Regulatory: RBI's microfinance lending guidelines (cap on margin, interest rate, repayment frequency). State‑level disruptions (e.g., Assam, Tamil Nadu) are binary events.""",
    aliases=["MFI", "MICRO_FINANCE"]
))

registry.register(SectorArchetype(
    "HOUSING_FINANCE",
    """NBFC with long‑duration assets (home loans), interest rate sensitive.
Metrics: Disbursement growth, spreads (yield on loans minus cost of borrowing), and asset quality (GNPA, NNPA).
Funding: Access to NHB refinance and bank securitisation is key. ALM mismatches – watch out for duration gap.
Red flags: Exposure to real estate developer loans (higher risk than retail home loans).""",
    aliases=["HFC", "HOUSING_FINANCE_COMPANY"]
))

registry.register(SectorArchetype(
    "VEHICLE_FINANCE",
    """Secured lending, but asset value depreciates.
Metrics: Collection efficiency (especially CV/CE), repossessed asset recovery rate, and used vehicle finance share.
Profitability: Yields are high (12‑18%) but credit costs spike during economic downturns.
Risk: Over‑exposure to commercial vehicles (cyclic), used car price volatility, and RBI risk weight changes.""",
    aliases=["AUTO_FINANCE", "CAR_LOAN", "CV_FINANCE"]
))

registry.register(SectorArchetype(
    "GOLD_LOAN_NBFC",
    """Low credit risk (LTV capped at 75%), high operating cost.
Metrics: AUM growth, LTV ratio (lower is safer), branch productivity per gram of gold.
Profitability: Net interest margin minus cost to income (high due to security, vault, appraiser costs).
Risk: Gold price crash leads to margin calls and auction losses. Regulatory cap on LTV/interest rate is a key monitorable.""",
    aliases=["GOLD_LOAN", "MANAPPURAM", "MUTHOOT"]
))

registry.register(SectorArchetype(
    "DEFAULT",
    """Apply standard fundamental analysis. Ensure Return on Invested Capital (ROIC) exceeds WACC.
Evaluate standard working capital efficiency, balance sheet leverage (Net Debt/EBITDA), and free cash flow generation."""
))

# ----------------------------------------------------------------------
# Public API for easy import
# ----------------------------------------------------------------------
def get_guardrails(sector_name: str, fuzzy: bool = True) -> str:
    """
    Convenience function to retrieve guardrails for a given sector.
    """
    return registry.get(sector_name, fuzzy=fuzzy)


def list_all_sectors() -> List[str]:
    """Return all registered sector names."""
    return registry.list_sectors()


if __name__ == "__main__":
    # Demo
    print("Available sectors (first 20):", list_all_sectors()[:20])
    print("\\n--- BFSI guardrails ---")
    print(get_guardrails("BFSI"))
    print("\\n--- Fuzzy match example: 'BANK' -> BFSI ---")
    print(get_guardrails("BANK"))
