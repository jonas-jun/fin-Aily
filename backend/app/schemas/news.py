from pydantic import BaseModel

from app.services.summarization_service import SummaryPoint


class SentimentOut(BaseModel):
    score: float
    label: str


class DigestOut(BaseModel):
    summary: list[SummaryPoint]
    sentiment: SentimentOut
    based_on_articles: int


class ArticleOut(BaseModel):
    id: int
    title: str
    source: str
    url: str
    published_at: str


class NewsResponse(BaseModel):
    symbol: str
    company_name: str
    last_updated: str
    digest: DigestOut
    articles: list[ArticleOut]
