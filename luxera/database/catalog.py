"""
Luxera Luminaire Catalog

SQLite-based luminaire database for storing and querying
photometric data from IES/LDT files.

Features:
- Import IES and LDT files
- Search by manufacturer, type, lumens, etc.
- Store embedded photometric data
- Export for project use
"""

from __future__ import annotations
import sqlite3
import json
import base64
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime


@dataclass
class LuminaireRecord:
    """A luminaire in the catalog."""
    id: Optional[int] = None
    catalog_number: str = ""
    manufacturer: str = ""
    name: str = ""
    description: str = ""
    
    # Physical
    width: float = 0.0
    length: float = 0.0
    height: float = 0.0
    weight: float = 0.0
    
    # Photometric
    lumens: float = 0.0
    watts: float = 0.0
    efficacy: float = 0.0  # lm/W
    cri: int = 80
    cct: int = 4000
    
    # Distribution
    distribution_type: str = ""  # Direct, Indirect, Direct/Indirect
    beam_angle: float = 0.0
    
    # File data
    file_type: str = "IES"  # IES or LDT
    file_content: str = ""  # Base64 encoded
    
    # Metadata
    category: str = ""
    tags: List[str] = field(default_factory=list)
    added_date: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['tags'] = json.dumps(self.tags)
        return d
    
    @staticmethod
    def from_dict(d: Dict[str, Any]) -> 'LuminaireRecord':
        if isinstance(d.get('tags'), str):
            d['tags'] = json.loads(d['tags'])
        return LuminaireRecord(**d)


class LuminaireCatalog:
    """SQLite-based luminaire catalog."""
    
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
    
    def _create_tables(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS luminaires (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_number TEXT,
                manufacturer TEXT,
                name TEXT,
                description TEXT,
                width REAL,
                length REAL,
                height REAL,
                weight REAL,
                lumens REAL,
                watts REAL,
                efficacy REAL,
                cri INTEGER,
                cct INTEGER,
                distribution_type TEXT,
                beam_angle REAL,
                file_type TEXT,
                file_content TEXT,
                category TEXT,
                tags TEXT,
                added_date TEXT
            )
        ''')
        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_manufacturer 
            ON luminaires(manufacturer)
        ''')
        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_lumens 
            ON luminaires(lumens)
        ''')
        self.conn.commit()
    
    def add(self, record: LuminaireRecord) -> int:
        """Add a luminaire to the catalog."""
        if not record.added_date:
            record.added_date = datetime.now().isoformat()
        
        d = record.to_dict()
        del d['id']
        
        cols = ', '.join(d.keys())
        placeholders = ', '.join(['?' for _ in d])
        
        cursor = self.conn.execute(
            f'INSERT INTO luminaires ({cols}) VALUES ({placeholders})',
            list(d.values())
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def get(self, id: int) -> Optional[LuminaireRecord]:
        """Get luminaire by ID."""
        row = self.conn.execute(
            'SELECT * FROM luminaires WHERE id = ?', (id,)
        ).fetchone()
        
        if row:
            return LuminaireRecord.from_dict(dict(row))
        return None
    
    def search(
        self,
        manufacturer: str = None,
        min_lumens: float = None,
        max_lumens: float = None,
        category: str = None,
        keyword: str = None,
        limit: int = 100
    ) -> List[LuminaireRecord]:
        """Search for luminaires."""
        query = 'SELECT * FROM luminaires WHERE 1=1'
        params = []
        
        if manufacturer:
            query += ' AND manufacturer LIKE ?'
            params.append(f'%{manufacturer}%')
        
        if min_lumens is not None:
            query += ' AND lumens >= ?'
            params.append(min_lumens)
        
        if max_lumens is not None:
            query += ' AND lumens <= ?'
            params.append(max_lumens)
        
        if category:
            query += ' AND category LIKE ?'
            params.append(f'%{category}%')
        
        if keyword:
            query += ' AND (name LIKE ? OR description LIKE ?)'
            params.extend([f'%{keyword}%', f'%{keyword}%'])
        
        query += f' LIMIT {limit}'
        
        rows = self.conn.execute(query, params).fetchall()
        return [LuminaireRecord.from_dict(dict(r)) for r in rows]
    
    def list_manufacturers(self) -> List[str]:
        """Get list of all manufacturers."""
        rows = self.conn.execute(
            'SELECT DISTINCT manufacturer FROM luminaires ORDER BY manufacturer'
        ).fetchall()
        return [r[0] for r in rows if r[0]]
    
    def count(self) -> int:
        """Get total number of luminaires."""
        return self.conn.execute(
            'SELECT COUNT(*) FROM luminaires'
        ).fetchone()[0]
    
    def delete(self, id: int) -> bool:
        """Delete a luminaire."""
        self.conn.execute('DELETE FROM luminaires WHERE id = ?', (id,))
        self.conn.commit()
        return True
    
    def close(self):
        self.conn.close()


def create_catalog(db_path: Path) -> LuminaireCatalog:
    """Create a new luminaire catalog."""
    return LuminaireCatalog(db_path)


def load_catalog(db_path: Path) -> LuminaireCatalog:
    """Load an existing catalog."""
    return LuminaireCatalog(db_path)


def save_catalog(catalog: LuminaireCatalog):
    """Save catalog (commits any pending changes)."""
    catalog.conn.commit()


def import_ies_to_catalog(
    catalog: LuminaireCatalog,
    ies_path: Path,
    category: str = "",
    tags: List[str] = None
) -> int:
    """
    Import an IES file into the catalog.
    
    Returns the ID of the added record.
    """
    from luxera.parser.ies_parser import parse_ies_text
    
    content = ies_path.read_text()
    doc = parse_ies_text(content)
    
    # Extract metadata
    manufacturer = doc.keywords.get('MANUFAC', ['Unknown'])[0]
    name = doc.keywords.get('LUMINAIRE', [''])[0]
    catalog_num = doc.keywords.get('LUMCAT', [''])[0]
    
    # Photometric data
    lumens = doc.photometry.lamp_lumens
    watts = doc.photometry.input_watts
    efficacy = lumens / watts if watts > 0 else 0
    
    # Dimensions
    width = doc.photometry.width
    length = doc.photometry.length
    height = doc.photometry.height
    
    record = LuminaireRecord(
        catalog_number=catalog_num,
        manufacturer=manufacturer,
        name=name,
        width=width,
        length=length,
        height=height,
        lumens=lumens,
        watts=watts,
        efficacy=efficacy,
        file_type='IES',
        file_content=base64.b64encode(content.encode()).decode(),
        category=category,
        tags=tags or [],
    )
    
    return catalog.add(record)
