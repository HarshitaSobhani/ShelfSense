import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded px-3 py-2 text-sm font-semibold ${isActive ? 'bg-forest-wash text-forest-dark' : 'text-ink-soft hover:text-forest'}`

export function Layout() {
  const { user, logout, ready } = useAuth()
  const [open, setOpen] = useState(false)
  const nav = useNavigate()

  const items = (
    <>
      <NavLink to="/discover" className={link}>
        Discover
      </NavLink>
      {user && (
        <>
          <NavLink to="/for-you" className={link}>
            For you
          </NavLink>
          <NavLink to="/library" className={link}>
            My shelf
          </NavLink>
        </>
      )}
      <NavLink to="/evaluation" className={link}>
        Evaluation
      </NavLink>
    </>
  )

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only-focusable btn m-2">
        Skip to content
      </a>
      <header className="border-b border-rule bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link to="/" className="font-display text-2xl font-semibold text-forest-dark">
            Shelf<span className="text-ember">Sense</span>
          </Link>
          <nav aria-label="Primary" className="hidden items-center gap-1 md:flex">
            {items}
          </nav>
          <div className="hidden items-center gap-2 md:flex">
            {!ready ? null : user ? (
              <>
                <NavLink to="/settings" className={link}>
                  {user.display_name}
                </NavLink>
                <button
                  className="btn btn-quiet"
                  onClick={async () => {
                    await logout()
                    nav('/')
                  }}
                >
                  Sign out
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="btn btn-quiet">
                  Sign in
                </Link>
                <Link to="/register" className="btn">
                  Join free
                </Link>
              </>
            )}
          </div>
          <button
            className="btn btn-quiet md:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen((o) => !o)}
          >
            {open ? 'Close' : 'Menu'}
          </button>
        </div>
        {open && (
          <nav id="mobile-nav" aria-label="Mobile" onClick={() => setOpen(false)} className="flex flex-col gap-1 border-t border-rule px-4 py-3 md:hidden">
            {items}
            {user ? (
              <>
                <NavLink to="/settings" className={link}>
                  Preferences &amp; goals
                </NavLink>
                <button
                  className="btn btn-quiet mt-1"
                  onClick={async () => {
                    await logout()
                    nav('/')
                  }}
                >
                  Sign out
                </button>
              </>
            ) : (
              <>
                <NavLink to="/login" className={link}>
                  Sign in
                </NavLink>
                <NavLink to="/register" className={link}>
                  Join free
                </NavLink>
              </>
            )}
          </nav>
        )}
      </header>
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet />
      </main>
      <footer className="border-t border-rule py-6 text-center text-sm text-ink-soft">
        ShelfSense · Seed catalog of real titles with hand-written tags · Optional Open Library import
      </footer>
    </div>
  )
}
