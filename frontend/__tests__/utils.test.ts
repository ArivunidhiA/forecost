import {
  formatCurrency,
  formatDate,
  getInitials,
  getProgressColor,
} from '@/lib/utils'

describe('Utility Functions', () => {
  describe('formatCurrency', () => {
    it('formats number as USD currency', () => {
      expect(formatCurrency(1000)).toBe('$1,000.00')
      expect(formatCurrency(1000.5)).toBe('$1,000.50')
    })

    it('handles zero', () => {
      expect(formatCurrency(0)).toBe('$0.00')
    })

    it('handles negative numbers', () => {
      expect(formatCurrency(-100)).toBe('-$100.00')
    })
  })

  describe('formatDate', () => {
    it('formats date string correctly', () => {
      const result = formatDate('2024-01-15T12:00:00Z')
      expect(result).toContain('Jan')
    })

    it('formats another date string correctly', () => {
      const result = formatDate('2024-06-20T12:00:00Z')
      expect(result).toContain('Jun')
    })
  })

  describe('getInitials', () => {
    it('returns initials from name', () => {
      expect(getInitials('John Doe')).toBe('JD')
      expect(getInitials('Jane Smith')).toBe('JS')
    })

    it('handles single name', () => {
      expect(getInitials('John')).toBe('J')
    })

    it('handles multiple spaces', () => {
      expect(getInitials('John Michael Doe')).toBe('JM')
    })
  })

  describe('getProgressColor', () => {
    it('returns green for low progress', () => {
      expect(getProgressColor(30)).toBe('bg-green-500')
    })

    it('returns green for progress below 80', () => {
      expect(getProgressColor(60)).toBe('bg-green-500')
    })

    it('returns yellow for progress at or above 80', () => {
      expect(getProgressColor(90)).toBe('bg-yellow-500')
    })

    it('returns red for progress at or above 100', () => {
      expect(getProgressColor(100)).toBe('bg-red-500')
    })
  })
})
