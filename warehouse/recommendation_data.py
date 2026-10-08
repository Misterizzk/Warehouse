"""Explicit demo demand and customer compatibility context for recommendations."""


def recommendation_context(db, material):
    """Return only the explicitly recorded demo scenario for one material.

    Site and customer labels are placeholders; an unknown material has no
    inferred destination. Customer demand is visible only through a material
    to unit-model compatibility record.
    """
    sites = [dict(row) for row in db.execute('''
        SELECT site,demand_prev,demand_now,open_demand,site_stock
        FROM site_demand WHERE material=? ORDER BY site''', (material,))]
    customers = [dict(row) for row in db.execute('''
        SELECT d.customer,d.unit_model,d.open_demand
        FROM material_unit_compatibility c
        JOIN customer_demand d ON d.unit_model=c.unit_model
        WHERE c.material=? ORDER BY d.customer,d.unit_model''', (material,))]
    return {'sites': sites, 'customers': customers, 'source': 'Simulasi'}
