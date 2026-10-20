export interface Book {
  id: number
  slug: string
  title: string
  subtitle: string | null
  description: string | null
  first_publish_year: number | null
  page_count: number | null
  cover_url: string | null
  pacing: 'slow' | 'medium' | 'fast' | null
  authors: string[]
  genres: string[]
  moods: string[]
  tropes: string[]
  content_warnings: string[]
  source: string
  has_embedding: boolean | null
}
export interface PageMeta { page: number; page_size: number; total: number; pages: number }
export interface Factor { factor: string; weight: number; value: number; contribution: number; evidence: string }
export interface RankedBook { book: Book; score: number; explanation: string; factors: Factor[] }
export interface SearchMeta extends PageMeta {
  mode_used: string
  semantic_available: boolean
  notice: string | null
  books_without_embeddings: number
  cold_start: boolean
}
export interface SearchOut { items: RankedBook[]; meta: SearchMeta }
export interface BrowseOut { items: Book[]; meta: PageMeta }
export interface FacetItem { name: string; count: number }
export interface Facets {
  genres: FacetItem[]; moods: FacetItem[]; tropes: FacetItem[]; content_warnings: FacetItem[]; pacing: FacetItem[]
  year_min: number | null; year_max: number | null
}
export type Status = 'want_to_read' | 'reading' | 'completed' | 'on_hold'
export const STATUS_LABEL: Record<Status, string> = {
  want_to_read: 'Want to read', reading: 'Reading', completed: 'Completed', on_hold: 'On hold',
}
export interface Entry {
  id: number; book: Book; status: Status; progress_percent: number; current_page: number | null
  started_at: string | null; finished_at: string | null; updated_at: string; rating: number | null
}
export interface LibraryOut { items: Entry[]; meta: PageMeta; counts: Record<Status, number> }
export interface MyBookState { entry: Entry | null; rating: number | null }
export interface Note { id: number; book_id: number; body: string; created_at: string; updated_at: string }
export interface Goal { year: number; target_books: number | null; completed: number }
export interface User { id: number; email: string; display_name: string; is_admin: boolean }
export interface AuthOut { user: User; csrf_token: string }
export interface Preferences {
  genres: string[]; moods: string[]; tropes: string[]; avoid_content_warnings: string[]; pacing: string | null
}
export interface Health {
  status: string
  database: boolean
  vector_backend: string | null
  semantic_search: {
    active: boolean; model: string; model_loaded: boolean; reason: string | null; setup: string | null
    indexed_books: number; total_books: number; stale_embeddings: number
  }
}
export interface ModeResult {
  mean: { recall: number; precision: number; mrr: number; ndcg: number }
  queries: { q: string; recall: number; precision: number; mrr: number; ndcg: number; top: string[]; relevant: string[] }[]
}
export interface EvalResults {
  k: number
  modes: Record<string, ModeResult>
  skipped_modes: { mode: string; reason: string }[]
  unresolved_titles: string[]
  query_count: number
  caveat: string
}
export interface EvalRun {
  id: number; created_at: string; k: number; catalog_size: number; embedding_model: string | null
  judgments_version: string; results: EvalResults
}
export interface EvalRuns { runs: EvalRun[]; judgments: { version: string; note: string; query_count: number } }
