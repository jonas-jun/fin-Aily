import type { Article } from "@/lib/api";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { RelativeTime } from "@/components/ui/RelativeTime";

function ArticleMeta({ source, publishedAt }: { source: string; publishedAt: string }) {
  return (
    <div className="flex items-center gap-1.5 mt-1 text-xs text-slate-400">
      <span>{source}</span>
      <RelativeTime value={publishedAt} prefix={<span>·</span>} />
    </div>
  );
}

interface Props {
  articles: Article[];
}

export function ArticleList({ articles }: Props) {
  return (
    <div>
      <h2 className="font-semibold text-slate-700 mb-3 flex items-center gap-2 text-sm">
        <span>📰</span>
        <span>Related Articles</span>
        <span className="text-xs font-normal text-slate-400">({articles.length})</span>
      </h2>

      <ul className="divide-y divide-slate-100">
        {articles.map((article) => (
          <li key={article.id} className="py-3 flex gap-2">
            {article.url ? (
              <ExternalLink
                href={article.url}
                className="group block flex-1 min-w-0"
              >
                <p className="text-sm font-medium text-slate-800 group-hover:text-brand-green transition-colors line-clamp-2 leading-snug">
                  {article.title}
                  <span className="ml-1.5 inline-block opacity-0 group-hover:opacity-60 transition-opacity text-brand-green text-xs">↗</span>
                </p>
                <ArticleMeta source={article.source} publishedAt={article.published_at} />
              </ExternalLink>
            ) : (
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-800 line-clamp-2 leading-snug">
                  {article.title}
                </p>
                <ArticleMeta source={article.source} publishedAt={article.published_at} />
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
