import { fireEvent, render, screen } from '@testing-library/react'
import { Cover } from '../components/Cover'

describe('Cover', () => {
  it('renders an accessible typographic fallback when there is no image', () => {
    render(<Cover book={{ title: 'Piranesi', authors: ['Susanna Clarke'], cover_url: null }} />)
    expect(screen.getByRole('img', { name: 'Cover of Piranesi by Susanna Clarke' })).toBeInTheDocument()
    expect(screen.getByText('Piranesi')).toBeInTheDocument()
  })

  it('falls back when the image fails to load', () => {
    render(<Cover book={{ title: 'Dune', authors: ['Frank Herbert'], cover_url: 'http://x/y.jpg' }} />)
    fireEvent.error(screen.getByAltText('Cover of Dune'))
    expect(screen.getByTestId('cover-fallback')).toBeInTheDocument()
  })

  it('is deterministic per title', () => {
    const { container, rerender } = render(<Cover book={{ title: 'Same', authors: [], cover_url: null }} />)
    const a = container.innerHTML
    rerender(<Cover book={{ title: 'Same', authors: [], cover_url: null }} />)
    expect(container.innerHTML).toBe(a)
  })
})
