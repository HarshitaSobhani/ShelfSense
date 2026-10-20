import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { Layout } from './components/Layout'
import { RequireAuth } from './components/RequireAuth'
import { Login, Register } from './pages/AuthPages'
import { BookDetail } from './pages/BookDetail'
import { Discover } from './pages/Discover'
import { Evaluation } from './pages/Evaluation'
import { ForYou } from './pages/ForYou'
import { Landing } from './pages/Landing'
import { Library } from './pages/Library'
import { NotFound } from './pages/NotFound'
import { Settings } from './pages/Settings'

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="discover" element={<Discover />} />
        <Route path="books/:id" element={<BookDetail />} />
        <Route path="login" element={<Login />} />
        <Route path="register" element={<Register />} />
        <Route path="evaluation" element={<Evaluation />} />
        <Route path="for-you" element={<RequireAuth><ForYou /></RequireAuth>} />
        <Route path="library" element={<RequireAuth><Library /></RequireAuth>} />
        <Route path="settings" element={<RequireAuth><Settings /></RequireAuth>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
