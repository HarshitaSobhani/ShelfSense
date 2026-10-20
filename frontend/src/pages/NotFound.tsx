import { Link } from 'react-router-dom'
import { EmptyState } from '../components/ui'

export function NotFound() {
  return (
    <EmptyState title="Page not found" action={<Link to="/" className="btn">Go home</Link>}>
      That page is not on any shelf.
    </EmptyState>
  )
}
