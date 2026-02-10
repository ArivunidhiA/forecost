import { render, screen } from '@testing-library/react'
import Button from '@/components/Button'

describe('Button Component', () => {
  it('renders button with text', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByRole('button')).toHaveTextContent('Click me')
  })

  it('renders with primary variant by default', () => {
    render(<Button>Primary</Button>)
    const button = screen.getByRole('button')
    expect(button).toHaveClass('bg-slate-900')
  })

  it('renders with secondary variant', () => {
    render(<Button variant="secondary">Secondary</Button>)
    const button = screen.getByRole('button')
    expect(button).toHaveClass('bg-slate-100')
  })

  it('disables button when disabled prop is true', () => {
    render(<Button disabled>Disabled</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('shows loading state when isLoading is true', () => {
    render(<Button isLoading>Loading</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('renders different sizes', () => {
    const { rerender } = render(<Button size="sm">Small</Button>)
    let button = screen.getByRole('button')
    expect(button).toHaveClass('px-3')

    rerender(<Button size="lg">Large</Button>)
    button = screen.getByRole('button')
    expect(button).toHaveClass('px-6')
  })
})
