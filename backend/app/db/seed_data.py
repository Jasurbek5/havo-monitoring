"""Boshlang'ich hududlar.

DIQQAT: koordinatalar tuman/shahar markazining TAXMINIY qiymatlari. Eng yaqin markazga
qarab hudud aniqlash tuman chegarasini aniq bermaydi. Ishlab chiqarishdan oldin
OpenStreetMap yoki rasmiy GeoJSON bilan tekshiring (README'dagi "Cheklovlar" bo'limi).
"""

from dataclasses import dataclass

from app.models.district import DistrictKind


@dataclass(frozen=True)
class DistrictSeed:
    slug: str
    name_uz: str
    name_ru: str
    name_en: str
    kind: DistrictKind
    lat: float
    lon: float


_C = DistrictKind.CITY_DISTRICT
_R = DistrictKind.REGION

DISTRICTS: list[DistrictSeed] = [
    # Toshkent shahri, 12 ta tuman
    DistrictSeed("bektemir", "Bektemir", "Бектемир", "Bektemir", _C, 41.209, 69.334),
    DistrictSeed("chilonzor", "Chilonzor", "Чиланзар", "Chilanzar", _C, 41.275, 69.204),
    DistrictSeed("mirobod", "Mirobod", "Мирабад", "Mirabad", _C, 41.288, 69.278),
    DistrictSeed("mirzo-ulugbek", "Mirzo Ulug'bek", "Мирзо-Улугбек", "Mirzo Ulugbek", _C, 41.338, 69.335),
    DistrictSeed("olmazor", "Olmazor", "Алмазар", "Almazar", _C, 41.348, 69.230),
    DistrictSeed("sergeli", "Sergeli", "Сергели", "Sergeli", _C, 41.225, 69.220),
    DistrictSeed("shayxontohur", "Shayxontohur", "Шайхантахур", "Shaykhontohur", _C, 41.323, 69.238),
    DistrictSeed("uchtepa", "Uchtepa", "Учтепа", "Uchtepa", _C, 41.300, 69.165),
    DistrictSeed("yakkasaroy", "Yakkasaroy", "Яккасарай", "Yakkasaray", _C, 41.285, 69.257),
    DistrictSeed("yangihayot", "Yangihayot", "Янгихает", "Yangihayot", _C, 41.310, 69.135),
    DistrictSeed("yashnobod", "Yashnobod", "Яшнабад", "Yashnabad", _C, 41.297, 69.337),
    DistrictSeed("yunusobod", "Yunusobod", "Юнусабад", "Yunusabad", _C, 41.365, 69.285),
    # Viloyat markazlari (sinov uchun; ma'lumot faqat so'rov bo'yicha olinadi)
    DistrictSeed("andijon", "Andijon viloyati", "Андижанская область", "Andijan Region", _R, 40.782, 72.344),
    DistrictSeed("buxoro", "Buxoro viloyati", "Бухарская область", "Bukhara Region", _R, 39.775, 64.429),
    DistrictSeed("fargona", "Farg'ona viloyati", "Ферганская область", "Fergana Region", _R, 40.384, 71.784),
    DistrictSeed("jizzax", "Jizzax viloyati", "Джизакская область", "Jizzakh Region", _R, 40.116, 67.842),
    DistrictSeed("namangan", "Namangan viloyati", "Наманганская область", "Namangan Region", _R, 40.998, 71.673),
    DistrictSeed("navoiy", "Navoiy viloyati", "Навоийская область", "Navoi Region", _R, 40.084, 65.379),
    DistrictSeed("qashqadaryo", "Qashqadaryo viloyati", "Кашкадарьинская область", "Kashkadarya Region", _R, 38.861, 65.789),
    DistrictSeed("qoraqalpogiston", "Qoraqalpog'iston Respublikasi", "Республика Каракалпакстан", "Republic of Karakalpakstan", _R, 42.453, 59.610),
    DistrictSeed("samarqand", "Samarqand viloyati", "Самаркандская область", "Samarkand Region", _R, 39.654, 66.960),
    DistrictSeed("sirdaryo", "Sirdaryo viloyati", "Сырдарьинская область", "Syrdarya Region", _R, 40.490, 68.784),
    DistrictSeed("surxondaryo", "Surxondaryo viloyati", "Сурхандарьинская область", "Surkhandarya Region", _R, 37.224, 67.278),
    DistrictSeed("toshkent-viloyati", "Toshkent viloyati", "Ташкентская область", "Tashkent Region", _R, 41.039, 69.362),
    DistrictSeed("xorazm", "Xorazm viloyati", "Хорезмская область", "Khorezm Region", _R, 41.550, 60.633),
]
