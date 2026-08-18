"""
Content variation generator.
Creates multiple text variations of property listings,
keeping all factual details unchanged.
"""

import random
from typing import List, Optional

from loguru import logger


# Property facts (MUST never change)
PROPERTY_FACTS = {
    "location": "Бурштин, Івано-Франківська область",
    "type": "половина будинку",
    "price": "$25 000",
    "price_raw": 25000,
    "area": "59 м²",
    "land": "9 сотих",
    "rooms": "2 кімнати",
    "storage": "велика кладовка, яку можна переобладнати під кімнату",
    "kitchen": "кухня, ванна, туалет",
    "basement": "підвал + вихід на горище",
    "outbuildings": "сарай, город, місце під гараж",
    "condition": "будинок під ремонт",
    "heating": "центральне опалення відключене, газова труба біля будинку",
    "contact_name": "Олег",
    "contact_phone": "+380 50 725 95 19",
}


class ContentGenerator:
    """Generates multiple variations of property listing text."""

    def __init__(self, num_variations: int = 6):
        self.num_variations = num_variations
        self._generated: List[str] = []

    def generate(self) -> List[str]:
        """Generate N variations of the property listing."""
        variations = [
            self._variation_price_focus(),
            self._variation_land_focus(),
            self._variation_renovation_focus(),
            self._variation_area_focus(),
            self._variation_short(),
            self._variation_detailed(),
        ]

        # If we need more variations than predefined, shuffle and pad
        while len(variations) < self.num_variations:
            variations.append(self._variation_balanced())

        # Shuffle to avoid predictable order
        variations = variations[:self.num_variations]
        random.shuffle(variations)

        self._generated = variations
        logger.info(f"Generated {len(variations)} text variations")
        return variations

    def get_variation(self, index: int) -> str:
        """Get a specific variation by index."""
        if not self._generated:
            self.generate()
        idx = index % len(self._generated)
        return self._generated[idx]

    def _variation_price_focus(self) -> str:
        """Variation emphasizing the price."""
        f = PROPERTY_FACTS
        return (
            f"💰 Ціна: {f['price']}\n\n"
            f"🏡 ПРОДАЄТЬСЯ {f['type'].upper()} В {f['location'].upper()}\n\n"
            f"📐 Площа: {f['area']}\n"
            f"🌳 Земельна ділянка: {f['land']}\n"
            f"🛏 {f['rooms'].title()} + {f['storage']}\n"
            f"🍽 {f['kitchen'].title()}\n"
            f"⬇️ {f['basement'].title()}\n"
            f"🏚 {f['outbuildings'].title()}\n\n"
            f"🔧 {f['condition'].title()}\n"
            f"🔥 {f['heating'].title()}\n\n"
            f"📞 {f['contact_name']}: {f['contact_phone']}"
        )

    def _variation_land_focus(self) -> str:
        """Variation emphasizing the land plot."""
        f = PROPERTY_FACTS
        return (
            f"🏡 ПРОДАЄТЬСЯ {f['type'].upper()} В {f['location'].upper()}\n\n"
            f"🌳 ЗЕМЕЛЬНА ДІЛЯНКА — {f['land']}!\n\n"
            f"📐 Площа будинку: {f['area']}\n"
            f"💰 Ціна: {f['price']}\n"
            f"🛏 {f['rooms'].title()} + {f['storage']}\n"
            f"🍽 {f['kitchen'].title()}\n"
            f"⬇️ {f['basement'].title()}\n"
            f"🏚 {f['outbuildings'].title()}\n\n"
            f"🔧 {f['condition'].title()}\n"
            f"🔥 {f['heating'].title()}\n\n"
            f"📞 {f['contact_name']}: {f['contact_phone']}"
        )

    def _variation_renovation_focus(self) -> str:
        """Variation emphasizing renovation opportunity."""
        f = PROPERTY_FACTS
        return (
            f"🏡 ПРОДАЄТЬСЯ {f['type'].upper()} В {f['location'].upper()}\n\n"
            f"🔧 МОЖЛИВІСТЬ ЗРОБИТИ РЕМОНТ ПІД СЕБЕ!\n\n"
            f"📐 Площа: {f['area']}\n"
            f"🌳 Земля: {f['land']}\n"
            f"💰 Ціна: {f['price']}\n"
            f"🛏 {f['rooms'].title()} + {f['storage']}\n"
            f"🍽 {f['kitchen'].title()}\n"
            f"⬇️ {f['basement'].title()}\n"
            f"🏚 {f['outbuildings'].title()}\n\n"
            f"🔥 {f['heating'].title()}\n\n"
            f"📞 {f['contact_name']}: {f['contact_phone']}"
        )

    def _variation_area_focus(self) -> str:
        """Variation emphasizing area and layout."""
        f = PROPERTY_FACTS
        return (
            f"🏡 {f['type'].title()} — {f['area']} у {f['location']}\n\n"
            f"📐 Загальна площа: {f['area']}\n"
            f"🌳 Ділянка: {f['land']}\n"
            f"🛏 {f['rooms'].title()} + {f['storage']}\n"
            f"🍽 {f['kitchen'].title()}\n"
            f"⬇️ {f['basement'].title()}\n"
            f"🏚 {f['outbuildings'].title()}\n\n"
            f"💰 Ціна: {f['price']}\n"
            f"🔧 {f['condition'].title()}\n"
            f"🔥 {f['heating'].title()}\n\n"
            f"📞 {f['contact_name']}: {f['contact_phone']}"
        )

    def _variation_short(self) -> str:
        """Short variation of the listing."""
        f = PROPERTY_FACTS
        return (
            f"🏡 {f['type'].title()} в {f['location']}\n"
            f"💰 {f['price']} | 📐 {f['area']} | 🌳 {f['land']}\n"
            f"🛏 {f['rooms'].title()}\n"
            f"🔧 {f['condition'].title()}\n"
            f"📞 {f['contact_name']}: {f['contact_phone']}"
        )

    def _variation_detailed(self) -> str:
        """Detailed variation with extra information."""
        f = PROPERTY_FACTS
        return (
            f"══════════════════════════════\n"
            f"🏡 ПРОДАЄТЬСЯ {f['type'].upper()}\n"
            f"📍 {f['location'].upper()}\n"
            f"══════════════════════════════\n\n"
            f"💰 Ціна: {f['price']}\n\n"
            f"📐 Площа будинку: {f['area']}\n"
            f"🌳 Земельна ділянка: {f['land']}\n\n"
            f"🛏 Кімнати: {f['rooms'].title()}\n"
            f"📦 {f['storage'].title()}\n\n"
            f"🍽 {f['kitchen'].title()}\n"
            f"⬇️ {f['basement'].title()}\n\n"
            f"🏚 {f['outbuildings'].title()}\n\n"
            f"🔧 {f['condition'].title()}\n"
            f"🔥 {f['heating'].title()}\n\n"
            f"══════════════════════════════\n"
            f"📞 {f['contact_name']}: {f['contact_phone']}\n"
            f"══════════════════════════════"
        )

    def _variation_balanced(self) -> str:
        """A balanced variation mixing different elements."""
        f = PROPERTY_FACTS
        return (
            f"🏡 Продам {f['type']} у місті Бурштин\n"
            f"📍 {f['location']}\n\n"
            f"💰 {f['price']}\n"
            f"📐 {f['area']}, ділянка {f['land']}\n\n"
            f"✅ {f['rooms'].title()}\n"
            f"✅ {f['storage'].title()}\n"
            f"✅ {f['kitchen'].title()}\n"
            f"✅ {f['basement'].title()}\n"
            f"✅ {f['outbuildings'].title()}\n\n"
            f"⚠️ {f['condition'].title()}\n"
            f"⚠️ {f['heating'].title()}\n\n"
            f"📞 Телефонуйте: {f['contact_name']} {f['contact_phone']}"
        )

    def validate_text(self, text: str) -> List[str]:
        """
        Validate that a generated text contains all required facts.
        Returns list of validation errors (empty = valid).
        """
        errors = []
        f = PROPERTY_FACTS

        checks = [
            (f["location"], "Location"),
            (f["price"], "Price"),
            (f["area"], "Area"),
            (f["land"], "Land"),
            (f["contact_phone"], "Phone"),
            (f["contact_name"], "Contact name"),
        ]

        for value, name in checks:
            if value.lower() not in text.lower():
                errors.append(f"Missing {name}: {value}")

        return errors
